from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.cobranzas.models import GestionCobro
from apps.cobranzas.services import anular_pago, registrar_cobranza
from apps.core.audit import contexto_auditoria
from apps.core.models import AuditLog
from apps.facturacion.services.emision import crear_factura

U = get_user_model()
HOY = timezone.localdate()


def api_de(usuario):
    a = APIClient()
    a.force_authenticate(usuario)
    return a


class UsuariosTest(TestCase):
    def setUp(self):
        self.admin = U.objects.create_user("jefa", password="x" * 12, rol="administrador")
        self.api = api_de(self.admin)

    def test_solo_admin(self):
        tes = U.objects.create_user("tes", password="x" * 12, rol="tesorero")
        self.assertEqual(api_de(tes).get("/api/core/usuarios/").status_code, 403)

    def test_crear_y_cambiar_rol_queda_auditado(self):
        r = self.api.post("/api/core/usuarios/", {"username": "carla", "first_name": "Carla", "rol": "cobrador",
                                                  "password": "Hierro-2026-seguro"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn("password", r.json())
        uid = r.json()["id"]
        self.assertTrue(U.objects.get(pk=uid).check_password("Hierro-2026-seguro"))
        r = self.api.patch(f"/api/core/usuarios/{uid}/", {"rol": "tesorero", "motivo": "Ascenso"}, format="json")
        self.assertEqual(r.json()["rol"], "tesorero")
        log = AuditLog.objects.filter(modelo="core.Usuario", objeto_id=str(uid)).latest("id")
        self.assertEqual((log.cambios["rol"], log.usuario, log.motivo), (["cobrador", "tesorero"], self.admin, "Ascenso"))
        self.assertNotIn("password", str(log.cambios))

    def test_contrasena_debil_o_faltante(self):
        self.assertEqual(self.api.post("/api/core/usuarios/", {"username": "a", "rol": "cobrador"},
                                       format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/core/usuarios/", {"username": "a", "rol": "cobrador",
                                                               "password": "1234567890"}, format="json").status_code, 400)

    def test_no_puede_quitarse_admin_ni_desactivarse(self):
        url = f"/api/core/usuarios/{self.admin.pk}/"
        self.assertEqual(self.api.patch(url, {"is_active": False}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(url, {"rol": "cobrador"}, format="json").status_code, 400)

    def test_quitar_admin_quita_acceso_al_panel(self):
        otro = U.objects.create_user("otro", password="x" * 12, rol="administrador")
        self.assertTrue(otro.is_staff)
        self.api.patch(f"/api/core/usuarios/{otro.pk}/", {"rol": "cobrador"}, format="json")
        otro.refresh_from_db()
        self.assertFalse(otro.is_staff)


class HistorialFacturaTest(TestCase):
    def setUp(self):
        self.tes = U.objects.create_user("tes", password="x" * 12, rol="tesorero")
        self.cob = U.objects.create_user("cob", password="x" * 12, rol="cobrador")
        self.admin = U.objects.create_user("adm", password="x" * 12, rol="administrador")
        cli = Cliente.objects.create(ruc="80012345-0", razon_social="Constructora Ñandutí", tipo="pyme",
                                     condicion_pago="credito", plazo_dias=30, limite_credito=10**10, acepta_whatsapp=True)
        with contexto_auditoria(self.tes):
            self.f = crear_factura({"cliente": cli, "timbrado": "12345678", "establecimiento": "001",
                                    "punto_expedicion": "001", "numero": "0000001", "fecha_emision": HOY,
                                    "condicion": "credito", "plazo_dias": 30},
                                   [{"descripcion": "Varilla", "cantidad": 1, "precio_unitario": Decimal(5_000_000)}],
                                   usuario=self.tes)
        api_de(self.tes).patch(f"/api/facturacion/facturas/{self.f.pk}/",
                               {"fecha_vencimiento": (HOY + timedelta(days=45)).isoformat(),
                                "motivo": "Prórroga pedida por el cliente"}, format="json")
        with contexto_auditoria(self.tes):
            pago = registrar_cobranza(self.f, Decimal(1_000_000), "efectivo", usuario=self.tes)
            anular_pago(pago, "Error de carga")
        api_de(self.cob).post("/api/cobranzas/gestiones/", {
            "cliente": cli.pk, "facturas": [self.f.pk], "tipo": "llamada", "resultado": "promesa_pago",
            "promesa_fecha": (HOY + timedelta(days=5)).isoformat(), "promesa_monto": "5000000",
            "mensaje": "Promete pagar el viernes"}, format="json")

    def test_tesorero_ve_quien_cambio_estado_y_vencimiento(self):
        r = api_de(self.tes).get(f"/api/facturacion/facturas/{self.f.pk}/historial/").json()
        self.assertTrue(r["ver_auditoria"])
        cambios = [(a["usuario"], c["campo"], c["despues_valor"]) for a in r["auditoria"] for c in a["cambios"]]
        self.assertIn(("tes", "fecha_vencimiento", (HOY + timedelta(days=45)).isoformat()), cambios)
        self.assertIn(("tes", "estado", "pagada_parcial"), cambios)
        self.assertIn(("tes", "anulado", True), cambios)          # anulación del pago
        legibles = [(c["etiqueta"], c["antes"], c["despues"]) for a in r["auditoria"] for c in a["cambios"]]
        self.assertIn(("Estado", "Pendiente", "Pagada parcialmente"), legibles)
        self.assertIn(("Saldo", "Gs. 5.000.000", "Gs. 4.000.000"), legibles)
        self.assertIn(("Vencimiento", (HOY + timedelta(days=30)).strftime("%d/%m/%Y"),
                       (HOY + timedelta(days=45)).strftime("%d/%m/%Y")), legibles)
        # La factura nunca figura como "pagada" al crearse (antes de sumar sus ítems).
        self.assertNotIn("Pagada", [c["despues"] for a in r["auditoria"] for c in a["cambios"] if c["campo"] == "estado"])
        tipos = [e["tipo"] for e in r["linea_de_tiempo"]]
        self.assertIn("gestion", tipos)
        self.assertIn("pago", tipos)
        prorroga = next(a for a in r["auditoria"] if a["motivo"] == "Prórroga pedida por el cliente")
        self.assertEqual(prorroga["cambios"][0]["etiqueta"], "Vencimiento")

    def test_cobrador_ve_gestiones_y_pagos_pero_no_auditoria(self):
        r = api_de(self.cob).get(f"/api/facturacion/facturas/{self.f.pk}/historial/").json()
        self.assertFalse(r["ver_auditoria"])
        self.assertEqual(r["auditoria"], [])
        self.assertEqual({e["tipo"] for e in r["linea_de_tiempo"]}, {"gestion", "pago"})
        g = next(e for e in r["linea_de_tiempo"] if e["tipo"] == "gestion")
        self.assertEqual((g["usuario"], g["titulo"]), ("cob", "Llamada telefónica · Promesa de pago"))

    def test_gestiones_por_factura(self):
        GestionCobro.objects.create(cliente=self.f.cliente, tipo="nota_interna", mensaje="Otra factura")
        r = api_de(self.cob).get("/api/cobranzas/gestiones/", {"factura": self.f.pk}).json()
        self.assertEqual(r["count"], 1)

    def test_auditoria_filtrada_por_campo(self):
        r = api_de(self.admin).get("/api/core/auditoria/", {"campo": "fecha_vencimiento",
                                                           "modelo": "facturacion.Factura"}).json()
        self.assertTrue(all("fecha_vencimiento" in x["cambios"] for x in r["results"]))
        self.assertGreaterEqual(r["count"], 2)  # alta y prórroga

    def test_busqueda_de_facturas(self):
        api = api_de(self.cob)
        for q in ("001-001-0000001", "1", "Ñandutí", "80012345"):
            self.assertEqual(api.get("/api/facturacion/facturas/", {"q": q}).json()["count"], 1, q)
