from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.cobranzas.services import registrar_cobranza
from apps.facturacion.services.emision import crear_factura
from apps.intereses.models import AlertaTasa, TasaReferenciaBCP
from apps.intereses.services import ErrorTasaNoCargada, calcular_interes_moratorio


class Base(TestCase):
    def setUp(self):
        call_command("cargar_tasas_ejemplo", stdout=open("/dev/null", "w"))
        self.cliente = Cliente.objects.create(ruc="80012345-0", razon_social="Constructora Ñandutí", tipo="pyme",
                                              condicion_pago="credito", plazo_dias=60, limite_credito=10**12)
        self.n = 0

    def factura(self, total, emision, plazo=30, tasa="0", moneda="PYG"):
        """Factura a crédito por `total` (IVA incluido)."""
        self.n += 1
        datos = {"cliente": self.cliente, "timbrado": "12345678", "establecimiento": "001",
                 "punto_expedicion": "001", "numero": f"{self.n:07d}", "fecha_emision": emision,
                 "condicion": "credito", "plazo_dias": plazo, "moneda": moneda, "tasa_interes_anual": Decimal(tasa)}
        if moneda == "USD":
            datos["tipo_cambio"] = Decimal("7650")
        return crear_factura(datos, [{"descripcion": "Hierro", "cantidad": 1, "precio_unitario": Decimal(total)}])


class EjemplosReadmeTest(Base):
    def test_pyg_45_dias_tasa_pactada_ajustada_al_tope(self):
        f = self.factura(15_000_000, date(2026, 7, 11), tasa="30")       # vence 10/08/2026
        r = calcular_interes_moratorio(f, date(2026, 9, 24))
        self.assertTrue(r["aplica"])
        self.assertEqual(r["dias_atraso"], 45)
        self.assertEqual(r["capital"], Decimal(15_000_000))
        self.assertEqual((r["tope_bcp_anual"], r["tope_bcp_periodo"]), (Decimal("27.260"), "08/2026"))
        self.assertEqual(r["tasa_aplicada_anual"], Decimal("27.260"))
        self.assertTrue(r["tasa_ajustada"])
        self.assertEqual(r["interes_diario"], Decimal("11202.74"))     # 15.000.000 × 27,26% / 365
        self.assertEqual(r["interes_acumulado"], Decimal(504_123))     # 11.202,7397 × 45
        self.assertEqual(r["total"], Decimal(15_504_123))
        self.assertIn("supera el tope legal", r["alertas"][0])
        # La alerta queda registrada una sola vez aunque se recalcule.
        calcular_interes_moratorio(f, date(2026, 9, 30))
        self.assertEqual(AlertaTasa.objects.filter(factura=f, tipo="ajuste_tope").count(), 1)

    def test_usd_20_dias_sin_tasa_pactada(self):
        f = self.factura("25000", date(2026, 7, 21), moneda="USD")        # vence 20/08/2026
        r = calcular_interes_moratorio(f, date(2026, 9, 9))
        self.assertEqual(r["dias_atraso"], 20)
        self.assertEqual((r["tope_bcp_anual"], r["tope_usd_anual"]), (Decimal("11.250"), Decimal("12.00")))
        self.assertEqual(r["tasa_aplicada_anual"], Decimal("11.250"))  # el menor entre BCP y 1% mensual
        self.assertEqual(r["origen_tasa"], "tope_sin_tasa_pactada")
        self.assertEqual(r["interes_acumulado"], Decimal("154.11"))    # 25.000 × 11,25% / 365 × 20
        self.assertEqual(r["total"], Decimal("25154.11"))
        self.assertFalse(r["tasa_ajustada"])


class ReglasTest(Base):
    def test_tope_1_por_ciento_mensual_usd(self):
        TasaReferenciaBCP.objects.create(anio=2026, mes=9, moneda="USD", tasa_maxima_anual=Decimal("13.5"),
                                         fuente="prueba")
        f = self.factura("10000", date(2026, 8, 15), tasa="15", moneda="USD")  # vence 14/09/2026
        r = calcular_interes_moratorio(f, date(2026, 10, 14))
        self.assertEqual((r["tope_bcp_anual"], r["tope_aplicable_anual"]), (Decimal("13.500"), Decimal("12.00")))
        self.assertEqual(r["tasa_aplicada_anual"], Decimal("12.00"))
        self.assertIn("1% mensual", r["alertas"][0])
        self.assertEqual(r["interes_acumulado"], Decimal("98.63"))      # 10.000 × 12% / 365 × 30

    def test_tasa_pactada_menor_al_tope_se_respeta(self):
        f = self.factura(10_000_000, date(2026, 7, 11), tasa="18")
        r = calcular_interes_moratorio(f, date(2026, 8, 20))
        self.assertEqual((r["tasa_aplicada_anual"], r["tasa_ajustada"], r["alertas"]), (Decimal("18.000"), False, []))
        self.assertFalse(AlertaTasa.objects.exists())

    def test_no_vencida(self):
        f = self.factura(1_000_000, date(2026, 7, 11), tasa="20")
        self.assertFalse(calcular_interes_moratorio(f, date(2026, 8, 10))["aplica"])  # día del vencimiento
        r = calcular_interes_moratorio(f, date(2026, 8, 11))
        self.assertEqual((r["aplica"], r["dias_atraso"]), (True, 1))  # desde el día siguiente

    def test_pagos_parciales_sin_capitalizar(self):
        f = self.factura(10_000_000, date(2026, 7, 11), tasa="20")      # vence 10/08
        registrar_cobranza(f, Decimal(4_000_000), "efectivo", fecha=date(2026, 8, 25))
        f.refresh_from_db()
        r = calcular_interes_moratorio(f, date(2026, 9, 9))
        # 15 días sobre 10.000.000 + 15 días sobre 6.000.000, siempre a 20% anual sobre capital
        esperado = (Decimal(10_000_000) * 15 + Decimal(6_000_000) * 15) * Decimal("0.20") / 365
        self.assertEqual(r["interes_acumulado"], esperado.quantize(Decimal(1)))
        self.assertEqual(r["interes_acumulado"], Decimal(131_507))
        self.assertEqual(r["capital"], Decimal(6_000_000))
        self.assertEqual([t["dias"] for t in r["tramos"]], [15, 15])
        # El interés no se suma a la base: calcular dos veces más adelante es lineal en los días.
        r60 = calcular_interes_moratorio(f, date(2026, 10, 9))
        self.assertEqual(r60["interes_acumulado"] - r["interes_acumulado"],
                         (Decimal(6_000_000) * 30 * Decimal("0.20") / 365).quantize(Decimal(1)))

    def test_pago_antes_del_vencimiento_reduce_capital(self):
        f = self.factura(10_000_000, date(2026, 7, 11), tasa="20")
        registrar_cobranza(f, Decimal(2_000_000), "efectivo", fecha=date(2026, 8, 1))
        f.refresh_from_db()
        r = calcular_interes_moratorio(f, date(2026, 8, 20))
        self.assertEqual(r["tramos"][0]["capital"], Decimal(8_000_000))

    def test_factura_pagada_no_genera_interes(self):
        f = self.factura(1_000_000, date(2026, 7, 11), tasa="20")
        registrar_cobranza(f, Decimal(1_000_000), "efectivo", fecha=date(2026, 8, 5))
        f.refresh_from_db()
        self.assertFalse(calcular_interes_moratorio(f, date(2026, 9, 1))["aplica"])

    def test_tasa_de_mes_anterior_con_alerta(self):
        f = self.factura(5_000_000, date(2026, 10, 1), tasa="20")       # vence 31/10/2026: no hay tasa de octubre
        r = calcular_interes_moratorio(f, date(2026, 11, 10))
        self.assertEqual(r["tope_bcp_periodo"], "08/2026")
        self.assertIn("No está cargada la tasa BCP PYG de 10/2026", r["alertas"][0])
        self.assertTrue(AlertaTasa.objects.filter(factura=f, tipo="tasa_mes_anterior").exists())

    def test_sin_tasa_cargada(self):
        TasaReferenciaBCP.objects.all().delete()
        f = self.factura(5_000_000, date(2026, 7, 11), tasa="20")
        with self.assertRaises(ErrorTasaNoCargada):
            calcular_interes_moratorio(f, date(2026, 9, 1))

    def test_sin_tasa_pactada_configurable(self):
        from django.conf import settings
        f = self.factura(5_000_000, date(2026, 7, 11))
        with self.settings(CRM={**settings.CRM, "USAR_TASA_BCP_SIN_PACTO": False}):
            r = calcular_interes_moratorio(f, date(2026, 9, 1))
        self.assertFalse(r["aplica"])
        self.assertIn("no tiene tasa", r["motivo"])


class ApiTest(Base):
    def cliente_api(self, rol):
        u = get_user_model().objects.create_user(rol, password="x" * 12, rol=rol)
        api = APIClient()
        api.force_authenticate(u)
        return api

    def test_endpoint_interes_y_simulador(self):
        f = self.factura(15_000_000, date(2026, 7, 11), tasa="30")
        api = self.cliente_api("cobrador")
        r = api.get(f"/api/intereses/facturas/{f.pk}/", {"fecha": "2026-09-24"}).json()
        self.assertEqual((r["interes_acumulado"], r["total"], r["tasa_aplicada_anual"]),
                         ("504123.00", "15504123.00", "27.26"))
        self.assertEqual(api.get(f"/api/intereses/facturas/{f.pk}/", {"fecha": "24-09-2026"}).status_code, 400)
        alertas = api.get("/api/intereses/alertas/", {"revisada": "false"}).json()["results"]
        self.assertEqual(len(alertas), 1)

    def test_sin_tasa_responde_409(self):
        TasaReferenciaBCP.objects.all().delete()
        f = self.factura(5_000_000, date(2026, 7, 11), tasa="20")
        r = self.cliente_api("tesorero").get(f"/api/intereses/facturas/{f.pk}/", {"fecha": "2026-09-01"})
        self.assertEqual(r.status_code, 409)

    def test_solo_admin_carga_tasas(self):
        datos = {"anio": 2026, "mes": 11, "moneda": "PYG", "tasa_maxima_anual": "27.3", "fuente": "Res. BCP N° X"}
        self.assertEqual(self.cliente_api("tesorero").post("/api/intereses/tasas-bcp/", datos).status_code, 403)
        admin = self.cliente_api("administrador")
        self.assertEqual(admin.post("/api/intereses/tasas-bcp/", datos).status_code, 201)
        self.assertEqual(admin.post("/api/intereses/tasas-bcp/", datos).status_code, 400)  # mes duplicado
