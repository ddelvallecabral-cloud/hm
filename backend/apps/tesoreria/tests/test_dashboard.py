from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.cobranzas.services import registrar_cobranza
from apps.facturacion.models import Factura, OrdenCompra
from apps.facturacion.services.emision import crear_factura
from apps.intereses.models import TasaReferenciaBCP

HOY = timezone.localdate()


class Base(TestCase):
    def setUp(self):
        call_command("cargar_tasas_ejemplo", stdout=open("/dev/null", "w"))
        # Tasas para cualquier mes de vencimiento usado en los tests (relativos a hoy).
        for i in range(0, 8):
            d = (HOY.replace(day=1) - timedelta(days=31 * i))
            for m, t in (("PYG", "27.26"), ("USD", "11.25")):
                TasaReferenciaBCP.objects.get_or_create(anio=d.year, mes=d.month, moneda=m,
                                                        defaults={"tasa_maxima_anual": Decimal(t), "fuente": "test"})
        self.pyme = Cliente.objects.create(ruc="80012345-0", razon_social="Constructora Ñandutí", tipo="pyme",
                                           condicion_pago="credito", plazo_dias=30, limite_credito=10**12)
        self.particular = Cliente.objects.create(razon_social="Juan Pérez", tipo="particular")
        self.n = 0
        u = get_user_model().objects.create_user("cob", password="x" * 12, rol="cobrador")
        self.api = APIClient()
        self.api.force_authenticate(u)

    def factura(self, total, dias_atras, cliente=None, condicion="credito", tasa="20", moneda="PYG", **kw):
        self.n += 1
        cliente = cliente or self.pyme
        datos = {"cliente": cliente, "timbrado": "12345678", "establecimiento": "001", "punto_expedicion": "001",
                 "numero": f"{self.n:07d}", "fecha_emision": HOY - timedelta(days=dias_atras),
                 "condicion": condicion, "plazo_dias": 30 if condicion == "credito" else 0, "moneda": moneda,
                 "tasa_interes_anual": Decimal(tasa), **kw}
        if moneda == "USD":
            datos["tipo_cambio"] = Decimal("7650")
        return crear_factura(datos, [{"descripcion": "Hierro", "cantidad": 1, "precio_unitario": Decimal(total)}])


class DashboardTest(Base):
    def test_aging_interes_totales_y_filtro(self):
        corriente = self.factura(1_100_000, 10)                 # vence en 20 días
        a15 = self.factura(2_200_000, 45)                       # 15 días de atraso
        a45 = self.factura(3_300_000, 75)                       # 45
        a75 = self.factura(4_400_000, 105)                      # 75
        a120 = self.factura(5_500_000, 150)                     # 120
        usd = self.factura("1000", 50, moneda="USD")            # 20 días, USD
        pagada = self.factura(1_000_000, 50)
        registrar_cobranza(pagada, Decimal(1_000_000), "efectivo")
        r = self.api.get("/api/tesoreria/dashboard/").json()

        grupos = {g["rango"]: [f["numero"] for f in g["facturas"]] for g in r["aging"]}
        self.assertEqual(grupos["corriente"], [corriente.numero_completo])
        self.assertEqual(grupos["1-30"], [usd.numero_completo, a15.numero_completo] if usd.fecha_vencimiento < a15.fecha_vencimiento
                         else [a15.numero_completo, usd.numero_completo])
        self.assertEqual((grupos["31-60"], grupos["61-90"], grupos["90+"]),
                         ([a45.numero_completo], [a75.numero_completo], [a120.numero_completo]))

        f15 = next(f for g in r["aging"] for f in g["facturas"] if f["factura_id"] == a15.pk)
        esperado = (Decimal(2_200_000) * Decimal("0.20") / 365 * 15).quantize(Decimal(1))
        self.assertEqual((f15["dias_atraso"], f15["interes_mora"]), (15, f"{esperado:.2f}"))
        self.assertEqual(next(f for g in r["aging"] for f in g["facturas"] if f["factura_id"] == corriente.pk)
                         ["interes_mora"], "0.00")

        pyg = r["cartera"]["PYG"]
        self.assertEqual(pyg["total_por_cobrar"], "16500000.00")      # sin la pagada ni la USD
        self.assertEqual(pyg["corriente"], "1100000.00")
        self.assertEqual(pyg["vencido"], "15400000.00")
        self.assertEqual(r["cartera"]["USD"]["total_por_cobrar"], "1000.00")

        solo_usd = self.api.get("/api/tesoreria/dashboard/", {"moneda": "USD"}).json()
        self.assertEqual(list(solo_usd["cartera"]), ["USD"])
        self.assertEqual([f["moneda"] for g in solo_usd["aging"] for f in g["facturas"]], ["USD"])
        self.assertEqual(self.api.get("/api/tesoreria/dashboard/", {"moneda": "EUR"}).status_code, 400)

    def test_dso(self):
        self.factura(9_000_000, 60)                              # dentro de los últimos 90 días, impaga
        f = self.factura(3_000_000, 30)
        registrar_cobranza(f, Decimal(3_000_000), "efectivo", fecha=HOY - timedelta(days=10))  # cobrada a 20 días
        self.factura(500_000, 5, cliente=self.particular, condicion="contado")  # contado: no entra al DSO
        d = self.api.get("/api/tesoreria/dashboard/", {"moneda": "PYG"}).json()["dso"]["PYG"]
        # CxC crédito 9.000.000 / ventas crédito 12.000.000 × 90 = 67,5 días
        self.assertEqual((d["cuentas_por_cobrar_credito"], d["ventas_credito_periodo"], d["dso"]),
                         ("9000000.00", "12000000.00", "67.50"))
        self.assertEqual(d["dias_promedio_cobro_real"], "20.00")

    def test_corte_a_fecha_anterior(self):
        f = self.factura(2_000_000, 45)
        registrar_cobranza(f, Decimal(500_000), "efectivo", fecha=HOY - timedelta(days=2))
        antes = self.api.get("/api/tesoreria/dashboard/", {"fecha": (HOY - timedelta(days=5)).isoformat()}).json()
        self.assertEqual(antes["cartera"]["PYG"]["total_por_cobrar"], "2000000.00")
        hoy = self.api.get("/api/tesoreria/dashboard/").json()
        self.assertEqual(hoy["cartera"]["PYG"]["total_por_cobrar"], "1500000.00")

    def test_csv(self):
        self.factura(2_200_000, 45)
        r = self.api.get("/api/tesoreria/dashboard/", {"formato": "csv"})
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")
        contenido = r.content.decode("utf-8-sig").splitlines()
        self.assertTrue(contenido[0].startswith("Aging;Factura;Cliente"))
        self.assertIn("1-30;001-001-0000001;Constructora Ñandutí;PYG", contenido[1])


class ReportesTest(Base):
    def test_estado_de_cuenta(self):
        vieja = self.factura(1_000_000, 100)
        registrar_cobranza(vieja, Decimal(400_000), "efectivo", fecha=HOY - timedelta(days=80))
        nueva = self.factura(2_000_000, 20)
        registrar_cobranza(nueva, Decimal(500_000), "transferencia", fecha=HOY - timedelta(days=5), referencia="T-1")
        desde = HOY - timedelta(days=30)
        r = self.api.get(f"/api/reportes/estado-cuenta/{self.pyme.pk}/", {"desde": desde.isoformat()}).json()
        pyg = r["monedas"]["PYG"]
        self.assertEqual(pyg["saldo_inicial"], "600000.00")
        self.assertEqual([(m["tipo"], m["debe"], m["haber"], m["saldo"]) for m in pyg["movimientos"]],
                         [("Factura", "2000000.00", "0.00", "2600000.00"), ("Pago", "0.00", "500000.00", "2100000.00")])
        self.assertEqual(pyg["saldo_final"], "2100000.00")
        self.assertEqual(len(r["facturas_pendientes"]), 2)
        self.assertNotEqual(r["interes_mora_total"]["PYG"], "0.00")
        csv = self.api.get(f"/api/reportes/estado-cuenta/{self.pyme.pk}/", {"desde": desde.isoformat(),
                                                                             "formato": "csv"})
        self.assertIn("Saldo inicial", csv.content.decode("utf-8-sig"))
        self.assertEqual(self.api.get(f"/api/reportes/estado-cuenta/{self.pyme.pk}/",
                                      {"desde": "2027-01-01", "hasta": "2026-01-01"}).status_code, 400)

    def test_iva_del_periodo(self):
        mes = date(2026, 6, 1)
        f1 = crear_factura({"cliente": self.particular, "timbrado": "12345678", "establecimiento": "001",
                            "punto_expedicion": "001", "numero": "0000101", "fecha_emision": mes,
                            "condicion": "contado"}, [{"descripcion": "Varilla", "cantidad": 1,
                                                       "precio_unitario": Decimal(11_000_000)}])
        crear_factura({"cliente": self.pyme, "timbrado": "12345678", "establecimiento": "001",
                       "punto_expedicion": "001", "numero": "0000102", "fecha_emision": date(2026, 6, 15),
                       "condicion": "contado", "moneda": "USD", "tipo_cambio": Decimal("7500"),
                       "porcentaje_retencion_iva": Decimal("30")},
                      [{"descripcion": "Chapa", "cantidad": 1, "precio_unitario": Decimal("1100")}])
        rech = crear_factura({"cliente": self.particular, "timbrado": "12345678", "establecimiento": "001",
                              "punto_expedicion": "001", "numero": "0000103", "fecha_emision": date(2026, 6, 20),
                              "condicion": "contado"}, [{"descripcion": "X", "cantidad": 1,
                                                         "precio_unitario": Decimal(1_100_000)}])
        Factura.objects.filter(pk=rech.pk).update(estado_sifen="rechazado")
        crear_factura({"cliente": self.particular, "timbrado": "12345678", "establecimiento": "001",
                       "punto_expedicion": "001", "numero": "0000104", "fecha_emision": date(2026, 7, 1),
                       "condicion": "contado"}, [{"descripcion": "Otro mes", "cantidad": 1, "precio_unitario": 1100}])
        r = self.api.get("/api/reportes/iva/", {"anio": 2026, "mes": 6}).json()
        self.assertEqual(r["cantidad_facturas"], 2)
        # PYG: base 10.000.000, IVA 1.000.000 · USD: base 1.000, IVA 100 × 7.500 = 7.500.000 / 750.000
        self.assertEqual((r["totales_gs"]["base_imponible"], r["totales_gs"]["debito_fiscal"]),
                         ("17500000.00", "1750000.00"))
        self.assertEqual(r["totales_gs"]["retencion_iva"], "225000.00")   # 30% de 750.000
        self.assertEqual(r["por_moneda"]["USD"]["iva"], "100.00")
        self.assertEqual([e["numero"] for e in r["excluidas_sifen"]], [rech.numero_completo])
        self.assertEqual(r["facturas"][0]["numero"], f1.numero_completo)
        self.assertEqual(self.api.get("/api/reportes/iva/", {"anio": 2026, "mes": 13}).status_code, 400)

    def test_oc_pendientes(self):
        oc = OrdenCompra.objects.create(cliente=self.pyme, numero="OC-9", fecha=HOY - timedelta(days=60),
                                        monto_total=10_000_000, obra_proyecto="Torre")
        con_saldo = self.factura(4_000_000, 40, orden_compra=oc)
        cobrada = self.factura(1_000_000, 40, orden_compra=oc)
        registrar_cobranza(cobrada, Decimal(1_000_000), "efectivo")
        self.factura(9_000_000, 10)                                # sin OC: no aparece
        r = self.api.get("/api/reportes/oc-pendientes/").json()
        self.assertEqual([f["factura"] for f in r["facturas_con_saldo"]], [con_saldo.numero_completo])
        self.assertEqual(r["facturas_con_saldo"][0]["dias_atraso"], 10)
        self.assertEqual(r["totales_facturas"]["PYG"], "4000000.00")
        self.assertEqual(r["ordenes_pendientes_de_facturar"][0]["pendiente_de_facturar"], "5000000.00")
