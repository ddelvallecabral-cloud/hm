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
        self.assertEqual(r.json()["factura"], f.pk)

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
    def pago(self, factura, monto, **kw):
        datos = {"factura": factura.pk, "fecha": HOY.isoformat(), "monto": str(monto),
                 "medio": "transferencia", "referencia": "SIPAP-001", **kw}
        return self.api.post(f"{P}pagos/", datos, format="json")

    def test_pago_parcial_y_luego_total(self):
        f = self.factura(self.pyme, 10_000_000, "credito", 30)
        r = self.pago(f, 4_000_000)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["factura_estado"], r.json()["moneda"], r.json()["cliente"]),
                         ("pagada_parcial", "PYG", self.pyme.pk))
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pagada_parcial", Decimal(6_000_000)))
        self.pago(f, 6_000_000)
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pagada", 0))
        log = AuditLog.objects.filter(modelo="facturacion.Factura", objeto_id=str(f.pk)).latest("id")
        self.assertEqual(log.cambios["estado"], ["pagada_parcial", "pagada"])
        self.assertEqual(log.usuario, self.tesorero)
        self.assertEqual(f.pagos.count(), 2)

    def test_no_supera_saldo_de_factura(self):
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        r = self.pago(f, 2_000_000)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Pago.objects.count(), 0)

    def test_factura_pagada_no_admite_pagos(self):
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        self.pago(f, 1_000_000)
        self.assertEqual(self.pago(f, 1).status_code, 400)

    def test_moneda_distinta(self):
        f = self.factura(self.pyme, 1_000, "credito", 30, moneda="USD")
        r = self.pago(f, 100, moneda="PYG")
        self.assertEqual(r.status_code, 400)
        self.assertIn("moneda", r.json())
        r = self.pago(f, "100.50")
        self.assertEqual((r.status_code, r.json()["moneda"]), (201, "USD"))

    def test_anular_pago_restituye_saldo(self):
        f = self.factura(self.pyme, 2_000_000, "credito", 30)
        pid = self.pago(f, 2_000_000).json()["id"]
        self.assertEqual(self.api.post(f"{P}pagos/{pid}/anular/", {}, format="json").status_code, 400)
        r = self.api.post(f"{P}pagos/{pid}/anular/", {"motivo": "Cheque rechazado"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        f.refresh_from_db()
        self.assertEqual((f.estado, f.saldo), ("pendiente", Decimal(2_000_000)))

    def test_pago_parcial_en_factura_vencida(self):
        f = self.factura(self.pyme, 2_000_000, "credito", 30, emision=HOY - timedelta(days=40))
        self.assertEqual(f.estado, "vencida")
        self.pago(f, 500_000)
        f.refresh_from_db()
        self.assertEqual((f.estado, f.monto_cobrado), ("vencida_pago_parcial", Decimal(500_000)))
        self.assertEqual(f.get_estado_display(), "Vencida y en proceso de pago parcial")

    def test_listado_por_factura_y_cliente(self):
        f1 = self.factura(self.pyme, 1_000_000, "credito", 30)
        f2 = self.factura(self.particular, 1_000_000)
        self.pago(f1, 100_000)
        self.api.post(f"{P}cobro-contado/", {"factura": f2.pk, "medio": "efectivo"}, format="json")
        self.assertEqual(self.api.get(f"{P}pagos/", {"factura": f1.pk}).json()["count"], 1)
        self.assertEqual(self.api.get(f"{P}pagos/", {"cliente": self.particular.pk}).json()["count"], 1)

    def test_cuenta_corriente(self):
        f = self.factura(self.pyme, 3_000_000, "credito", 30, emision=HOY - timedelta(days=40))
        self.pago(f, 1_000_000)
        cc = self.api.get(f"{P}cuenta-corriente/{self.pyme.pk}/").json()["monedas"]["PYG"]
        self.assertEqual((cc["saldo_pendiente"], cc["saldo_vencido"]), ("2000000.00", "2000000.00"))
        self.assertEqual(cc["ultimos_pagos"][0]["factura"], f.numero_completo)

    def test_alertas(self):
        self.factura(self.pyme, 1_000_000, "credito", 30, emision=HOY - timedelta(days=27))  # vence en 3 días
        self.factura(self.pyme, 1_000_000, "credito", 30, emision=HOY - timedelta(days=35))  # vencida hace 5
        r = self.api_cob.get(f"{P}alertas/").json()
        self.assertEqual(len(r["proximas_a_vencer"]), 1)
        self.assertEqual(r["vencidas"][0]["dias_atraso"], 5)


class RegistrarCobranzaTest(Base):
    URL = f"{P}registrar-cobranza/"

    def test_pago_parcial_y_total(self):
        f = self.factura(self.pyme, 10_000_000, "credito", 30)
        r = self.api.post(self.URL, {"factura": f.pk, "monto": "4000000", "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["factura"]["estado"], r.json()["factura"]["saldo"]), ("pagada_parcial", "6000000.00"))
        self.assertEqual(r.json()["pago"]["moneda"], "PYG")
        r = self.api.post(self.URL, {"factura": f.pk, "monto": "6000000", "medio": "cheque", "referencia": "CH 0012"},
                          format="json")
        self.assertEqual((r.json()["factura"]["estado"], r.json()["factura"]["saldo"]), ("pagada", "0.00"))

    def test_monto_mayor_al_saldo(self):
        f = self.factura(self.particular, 1_000_000)
        r = self.api.post(self.URL, {"factura": f.pk, "monto": "1000001", "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("monto", r.json())

    def test_moneda_distinta(self):
        f = self.factura(self.pyme, 1_000, "credito", 30, moneda="USD")
        r = self.api.post(self.URL, {"factura": f.pk, "monto": "100", "medio": "efectivo", "moneda": "PYG"},
                          format="json")
        self.assertEqual(r.status_code, 400)

    def test_cobrador_no_registra(self):
        f = self.factura(self.particular, 1_000_000)
        r = self.api_cob.post(self.URL, {"factura": f.pk, "monto": "1", "medio": "efectivo"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_saldo_pendiente_calculado_desde_pagos(self):
        from apps.cobranzas.services import saldo_pendiente
        f = self.factura(self.pyme, 9_000_000, "credito", 30)
        self.api.post(self.URL, {"factura": f.pk, "monto": "2000000", "medio": "efectivo",
                                 "fecha": (HOY + timedelta(days=1)).isoformat()}, format="json")
        f.refresh_from_db()
        self.assertEqual(saldo_pendiente(f), Decimal(7_000_000))
        self.assertEqual(saldo_pendiente(f, al=HOY), Decimal(9_000_000))  # saldo a una fecha anterior al pago

    def test_buscar_por_cliente_ruc_y_numero(self):
        f = self.factura(self.pyme, 1_000_000, "credito", 30)
        self.factura(self.particular, 1_000_000)
        buscar = lambda q: [x["numero"] for x in self.api_cob.get(f"{P}facturas-por-cobrar/", {"q": q}).json()]
        self.assertEqual(buscar("ñandutí"), [f.numero_completo])
        self.assertEqual(buscar("80012345"), [f.numero_completo])
        self.assertEqual(buscar(f.numero_completo), [f.numero_completo])
        self.assertEqual(buscar(str(int(f.numero))), [f.numero_completo])
        self.assertEqual(len(buscar("")), 2)


class SesionTest(TestCase):
    def test_login_csrf_y_me(self):
        get_user_model().objects.create_user("ana", password="clave-segura-123", rol="tesorero")
        c = APIClient(enforce_csrf_checks=True)
        c.get("/api/core/csrf/")
        token = c.cookies["csrftoken"].value
        self.assertEqual(c.post("/api/core/login/", {"username": "ana", "password": "mal"}, format="json",
                                HTTP_X_CSRFTOKEN=token).status_code, 400)
        r = c.post("/api/core/login/", {"username": "ana", "password": "clave-segura-123"}, format="json",
                   HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.json()["rol"], "tesorero")
        self.assertEqual(c.get("/api/core/me/").json()["username"], "ana")


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

    def alertas(self, r):
        self.assertEqual(r.status_code, 201, r.content)
        return {a["codigo"] for a in r.json()["alertas"]}

    def test_mensaje_sensible_genera_alerta_y_no_bloquea(self):
        r = self.gestion(mensaje="Si no paga hoy le vamos a embargar y avisaremos a su empleador")
        self.assertEqual(self.alertas(r), {"expresiones"})
        self.assertEqual(r.json()["revision"], "pendiente")

    def test_gestion_correcta_sin_alertas(self):
        r = self.gestion(mensaje="Le recordamos el vencimiento de su factura.")
        self.assertEqual(self.alertas(r), set())
        self.assertEqual(r.json()["revision"], "no_requiere")

    def test_fuera_de_horario_alerta(self):
        self.assertEqual(self.alertas(self.gestion(fecha_hora=proximo(1, time(21, 30)).isoformat())), {"horario"})
        self.assertEqual(self.alertas(self.gestion(fecha_hora=proximo(5, time(15, 0)).isoformat())), {"horario"})
        self.assertEqual(self.alertas(self.gestion(fecha_hora=proximo(6).isoformat())), {"dia"})

    def test_nota_interna_sin_alertas_de_horario(self):
        r = self.gestion(tipo="nota_interna", fecha_hora=proximo(6, time(22, 0)).isoformat())
        self.assertEqual(self.alertas(r), set())

    def test_feriado_alerta(self):
        Feriado.objects.create(fecha=proximo(1).date(), descripcion="Feriado de prueba")
        self.assertEqual(self.alertas(self.gestion()), {"dia"})

    def test_frecuencia_alerta(self):
        base = proximo(0)
        for i in range(3):
            self.assertEqual(self.alertas(self.gestion(fecha_hora=(base + timedelta(hours=i)).isoformat())), set())
        self.assertEqual(self.alertas(self.gestion(fecha_hora=(base + timedelta(days=1)).isoformat())), {"frecuencia"})

    def test_whatsapp_sin_consentimiento_alerta(self):
        self.assertEqual(self.alertas(self.gestion(cliente=self.particular.pk, tipo="whatsapp")), {"whatsapp"})
        self.assertEqual(self.alertas(self.gestion(tipo="whatsapp")), set())

    def test_tesoreria_revisa_y_decide_el_mensaje(self):
        gid = self.gestion(mensaje="Último aviso antes de iniciar acciones").json()["id"]
        url = f"{P}gestiones/{gid}/revisar/"
        self.assertEqual(self.api_cob.post(url, {"decision": "aprobada"}, format="json").status_code, 403)
        self.assertEqual(self.api.post(url, {"decision": "modificada"}, format="json").status_code, 400)
        r = self.api.post(url, {"decision": "modificada", "comentario": "Tono más cordial",
                                "mensaje_final": "Le escribimos por la factura pendiente; ¿coordinamos el pago?"},
                          format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual((d["revision"], d["revisada_por_nombre"]), ("modificada", "tes"))
        self.assertTrue(d["mensaje_final"].startswith("Le escribimos"))
        self.assertTrue(AuditLog.objects.filter(modelo="cobranzas.GestionCobro", objeto_id=str(gid),
                                                motivo__startswith="Revisión").exists())
        self.assertEqual(len(self.api.get(f"{P}gestiones/", {"revision": "pendiente"}).json()["results"]), 0)

    def test_verificar_sin_guardar(self):
        r = self.api_cob.post(f"{P}gestiones/verificar/", {"cliente": self.pyme.pk, "tipo": "llamada",
                                                            "fecha_hora": proximo(6).isoformat(),
                                                            "mensaje": "lo vamos a denunciar a la policía"},
                              format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({a["codigo"] for a in r.json()["alertas"]}, {"dia", "expresiones"})
        self.assertEqual(GestionCobro.objects.count(), 0)

    def test_recomendacion_por_tramo(self):
        f = self.factura(self.pyme, 3_300_000, "credito", 30, emision=HOY - timedelta(days=50))  # 20 días de atraso
        r = self.api_cob.get(f"{P}recomendaciones/", {"factura": f.pk}).json()
        self.assertEqual((r["tramo"], r["dias_atraso"]), ("atraso_moderado", 20))
        self.assertIn("3.300.000", r["mensaje_sugerido"])
        self.assertIn(f.numero_completo, r["mensaje_sugerido"])
        # La recomendación misma no dispara alertas.
        g = self.gestion(mensaje=r["mensaje_sugerido"])
        self.assertEqual(self.alertas(g), set())

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
