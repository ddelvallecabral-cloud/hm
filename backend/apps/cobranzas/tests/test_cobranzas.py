from datetime import datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.cobranzas.models import Feriado, GestionCobro, Pago
from apps.core.models import AuditLog
from apps.facturacion.models import Factura
from apps.facturacion.services.emision import crear_factura

TZ = ZoneInfo("America/Asuncion")
HOY = timezone.localdate()
P = "/api/cobranzas/"


def proximo(dia_semana, hora=time(10, 0)):
    """Próxima fecha (desde mañana) con ese día de la semana (0 = lunes), en hora de Asunción."""
    d = HOY + timedelta(days=1)
    while d.weekday() != dia_semana:
        d += timedelta(days=1)
    return datetime.combine(d, hora, tzinfo=TZ)


class Base(TestCase):
    def setUp(self):
        U = get_user_model()
        self.tesorero = U.objects.create_user("tes", password="x" * 12, rol="tesorero")
        self.cobrador = U.objects.create_user("cob", password="x" * 12, rol="cobrador")
        self.api = APIClient()
        self.api.force_authenticate(self.tesorero)
        self.api_cob = APIClient()
        self.api_cob.force_authenticate(self.cobrador)
        self.particular = Cliente.objects.create(razon_social="Juan Pérez", tipo="particular")
        self.pyme = Cliente.objects.create(ruc="80012345-0", razon_social="Constructora Ñandutí", tipo="pyme",
                                           condicion_pago="credito", plazo_dias=60, limite_credito=100_000_000,
                                           acepta_whatsapp=True)
        self.n = 0

    def factura(self, cliente, monto, condicion="contado", plazo=0, emision=None, moneda="PYG"):
        self.n += 1
        datos = {"cliente": cliente, "timbrado": "12345678", "establecimiento": "001", "punto_expedicion": "001",
                 "numero": f"{self.n:07d}", "fecha_emision": emision or HOY, "condicion": condicion,
                 "plazo_dias": plazo, "moneda": moneda}
        if moneda == "USD":
            datos["tipo_cambio"] = Decimal("7800")
        return crear_factura(datos, [{"descripcion": "Hierro", "cantidad": 1, "precio_unitario": monto}])


class CobroContadoTest(Base):
    def test_cobro_contado_deja_factura_pagada(self):
        f = self.factura(self.particular, 2_200_000)
        r = self.api.post(f"{P}cobro-contado/", {"factura": f.pk, "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pagada", 0))
        self.assertEqual(r.json()["monto"], "2200000.00")
        self.assertEqual(r.json()["monto_sin_aplicar"], "0.00")

    def test_no_cobra_dos_veces(self):
        f = self.factura(self.particular, 1_000_000)
        self.api.post(f"{P}cobro-contado/", {"factura": f.pk, "medio": "efectivo"}, format="json")
        r = self.api.post(f"{P}cobro-contado/", {"factura": f.pk, "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_credito_no_usa_cobro_contado(self):
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        r = self.api.post(f"{P}cobro-contado/", {"factura": f.pk, "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_transferencia_exige_referencia(self):
        f = self.factura(self.particular, 1_000_000)
        r = self.api.post(f"{P}cobro-contado/", {"factura": f.pk, "medio": "transferencia"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("referencia", r.json())

    def test_cobrador_no_registra_pagos(self):
        f = self.factura(self.particular, 1_000_000)
        r = self.api_cob.post(f"{P}cobro-contado/", {"factura": f.pk, "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 403)


class PagosParcialesTest(Base):
    def pago(self, monto, **kw):
        datos = {"cliente": self.pyme.pk, "fecha": HOY.isoformat(), "moneda": "PYG", "monto": str(monto),
                 "medio": "transferencia", "referencia": "SIPAP-001", **kw}
        return self.api.post(f"{P}pagos/", datos, format="json")

    def test_pago_parcial_y_luego_total(self):
        f = self.factura(self.pyme, 10_000_000, "credito", 30)
        r = self.pago(4_000_000, imputaciones=[{"factura": f.pk, "monto": "4000000"}])
        self.assertEqual(r.status_code, 201, r.content)
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pagada_parcial", Decimal(6_000_000)))
        self.pago(6_000_000, imputaciones=[{"factura": f.pk, "monto": "6000000"}])
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pagada", 0))
        log = AuditLog.objects.filter(modelo="facturacion.Factura", objeto_id=str(f.pk)).latest("id")
        self.assertEqual(log.cambios["estado"], ["pagada_parcial", "pagada"])
        self.assertEqual(log.usuario, self.tesorero)

    def test_no_supera_saldo_de_factura(self):
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        r = self.pago(2_000_000, imputaciones=[{"factura": f.pk, "monto": "2000000"}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pago.objects.count(), 0)  # la transacción revirtió el pago

    def test_imputacion_automatica_mas_antigua_primero(self):
        vieja = self.factura(self.pyme, 3_000_000, "credito", 30, emision=HOY - timedelta(days=20))
        nueva = self.factura(self.pyme, 5_000_000, "credito", 30)
        r = self.pago(4_000_000, aplicar_automatico=True)
        self.assertEqual(r.status_code, 201, r.content)
        vieja.refresh_from_db()
        nueva.refresh_from_db()
        self.assertEqual(vieja.estado, "pagada")
        self.assertEqual(nueva.saldo, Decimal(4_000_000))

    def test_saldo_a_favor_y_aplicacion_posterior(self):
        r = self.pago(1_500_000)
        pid = r.json()["id"]
        self.assertEqual(r.json()["monto_sin_aplicar"], "1500000.00")
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        r = self.api.post(f"{P}pagos/{pid}/aplicar/", {"imputaciones": [{"factura": f.pk, "monto": "1000000"}]},
                          format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["monto_sin_aplicar"], "500000.00")
        cc = self.api.get(f"{P}cuenta-corriente/{self.pyme.pk}/").json()
        self.assertEqual(cc["monedas"]["PYG"]["saldo_a_favor"], "500000.00")

    def test_moneda_distinta(self):
        f = self.factura(self.pyme, 1_000, "credito", 30, moneda="USD")
        r = self.pago(1_000_000, imputaciones=[{"factura": f.pk, "monto": "1000"}])
        self.assertEqual(r.status_code, 400)

    def test_anular_pago_restituye_saldo(self):
        f = self.factura(self.pyme, 2_000_000, "credito", 30)
        pid = self.pago(2_000_000, imputaciones=[{"factura": f.pk, "monto": "2000000"}]).json()["id"]
        self.assertEqual(self.api.post(f"{P}pagos/{pid}/anular/", {}, format="json").status_code, 400)
        r = self.api.post(f"{P}pagos/{pid}/anular/", {"motivo": "Cheque rechazado"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pendiente", Decimal(2_000_000)))

    def test_pago_parcial_en_factura_vencida_sigue_vencida(self):
        f = self.factura(self.pyme, 2_000_000, "credito", 30, emision=HOY - timedelta(days=40))
        self.assertEqual(f.estado, "vencida")
        self.pago(500_000, imputaciones=[{"factura": f.pk, "monto": "500000"}])
        f.refresh_from_db()
        self.assertEqual((f.estado, f.monto_cobrado), ("vencida", Decimal(500_000)))

    def test_alertas(self):
        self.factura(self.pyme, 1_000_000, "credito", 30, emision=HOY - timedelta(days=27))  # vence en 3 días
        self.factura(self.pyme, 1_000_000, "credito", 30, emision=HOY - timedelta(days=35))  # vencida hace 5
        r = self.api_cob.get(f"{P}alertas/").json()
        self.assertEqual(len(r["proximas_a_vencer"]), 1)
        self.assertEqual(r["vencidas"][0]["dias_atraso"], 5)


class GestionesTest(Base):
    def gestion(self, api=None, **kw):
        datos = {"cliente": self.pyme.pk, "tipo": "llamada", "fecha_hora": proximo(1).isoformat(), **kw}
        return (api or self.api_cob).post(f"{P}gestiones/", datos, format="json")

    def test_cobrador_registra_promesa(self):
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        r = self.gestion(facturas=[f.pk], resultado="promesa_pago",
                         promesa_fecha=(proximo(1) + timedelta(days=3)).date().isoformat(), promesa_monto="1000000",
                         mensaje="Le recordamos que su factura vence pronto.")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["cobrador_nombre"], "cob")

    def test_promesa_sin_fecha(self):
        self.assertEqual(self.gestion(resultado="promesa_pago").status_code, 400)

    def test_mensaje_intimidatorio_rechazado(self):
        r = self.gestion(mensaje="Si no paga hoy le vamos a embargar y avisaremos a su empleador")
        self.assertEqual(r.status_code, 400)
        self.assertIn("mensaje", r.json())

    def test_fuera_de_horario(self):
        self.assertEqual(self.gestion(fecha_hora=proximo(1, time(21, 30)).isoformat()).status_code, 400)
        self.assertEqual(self.gestion(fecha_hora=proximo(5, time(15, 0)).isoformat()).status_code, 400)  # sábado tarde
        self.assertEqual(self.gestion(fecha_hora=proximo(6).isoformat()).status_code, 400)  # domingo

    def test_nota_interna_sin_restriccion_horaria(self):
        self.assertEqual(self.gestion(tipo="nota_interna", fecha_hora=proximo(6, time(22, 0)).isoformat())
                         .status_code, 201)

    def test_feriado(self):
        Feriado.objects.create(fecha=proximo(1).date(), descripcion="Feriado de prueba")
        self.assertEqual(self.gestion().status_code, 400)

    def test_maximo_contactos_semanales(self):
        base = proximo(0)
        for i in range(3):
            self.assertEqual(self.gestion(fecha_hora=(base + timedelta(hours=i)).isoformat()).status_code, 201)
        r = self.gestion(fecha_hora=(base + timedelta(days=1)).isoformat())
        self.assertEqual(r.status_code, 400)
        self.assertIn("7 días", str(r.json()))

    def test_whatsapp_requiere_consentimiento(self):
        r = self.gestion(cliente=self.particular.pk, tipo="whatsapp")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.gestion(tipo="whatsapp").status_code, 201)

    def test_factura_de_otro_cliente(self):
        f = self.factura(self.particular, 1_000_000)
        self.assertEqual(self.gestion(facturas=[f.pk]).status_code, 400)

    def test_evaluar_promesas(self):
        g = GestionCobro.objects.create(cliente=self.pyme, tipo="nota_interna", resultado="promesa_pago",
                                        fecha_hora=timezone.now() - timedelta(days=10),
                                        promesa_fecha=HOY - timedelta(days=2), promesa_monto=1_000_000)
        call_command("evaluar_promesas", stdout=StringIO())
        g.refresh_from_db()
        self.assertIs(g.promesa_cumplida, False)

    def test_cobrador_solo_edita_sus_gestiones(self):
        gid = self.gestion(api=self.api).json()["id"]  # creada por el tesorero
        r = self.api_cob.patch(f"{P}gestiones/{gid}/", {"resultado": "contactado"}, format="json")
        self.assertEqual(r.status_code, 404)
