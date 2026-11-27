from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.core.audit import contexto_auditoria
from apps.core.models import AuditLog

Usuario = get_user_model()


def cliente_api(rol):
    u = Usuario.objects.create_user(rol, password="x" * 12, rol=rol)
    api = APIClient()
    api.force_authenticate(u)
    return api, u


PYME = {"ruc": "80012345-0", "razon_social": "Aceros del Sur S.A.", "tipo": "pyme"}


class RolesTest(TestCase):
    def test_cobrador_solo_lectura(self):
        api, _ = cliente_api("cobrador")
        self.assertEqual(api.get("/api/clientes/").status_code, 200)
        self.assertEqual(api.post("/api/clientes/", PYME, format="json").status_code, 403)

    def test_tesorero_crea(self):
        api, _ = cliente_api("tesorero")
        self.assertEqual(api.post("/api/clientes/", PYME, format="json").status_code, 201)

    def test_auditoria_solo_admin(self):
        self.assertEqual(cliente_api("tesorero")[0].get("/api/core/auditoria/").status_code, 403)
        self.assertEqual(cliente_api("administrador")[0].get("/api/core/auditoria/").status_code, 200)

    def test_admin_tiene_acceso_al_admin_django(self):
        _, u = cliente_api("administrador")
        self.assertTrue(u.is_staff)

    def test_me(self):
        api, _ = cliente_api("tesorero")
        r = api.get("/api/core/me/").json()
        self.assertEqual(r["rol"], "tesorero")
        self.assertTrue(r["es_tesorero"])
        self.assertFalse(r["es_administrador"])


class AuditoriaTest(TestCase):
    def test_alta_y_cambio_quedan_registrados_con_usuario_y_motivo(self):
        api, u = cliente_api("tesorero")
        cid = api.post("/api/clientes/", PYME, format="json").json()["id"]
        api.patch(f"/api/clientes/{cid}/", {"condicion_pago": "credito", "plazo_dias": 30,
                                            "limite_credito": "50000000", "motivo": "Aprobado por gerencia"},
                  format="json")
        logs = AuditLog.objects.filter(modelo="clientes.Cliente", objeto_id=str(cid)).order_by("id")
        self.assertEqual([l.accion for l in logs], ["crear", "modificar"])
        cambio = logs[1]
        self.assertEqual(cambio.usuario, u)
        self.assertEqual(cambio.motivo, "Aprobado por gerencia")
        self.assertEqual(cambio.cambios["plazo_dias"], [None, 30])
        self.assertEqual(cambio.cambios["condicion_pago"], ["contado", "credito"])
        self.assertNotIn("razon_social", cambio.cambios)

    def test_contexto_fuera_de_request(self):
        u = Usuario.objects.create_user("script", password="x" * 12)
        with contexto_auditoria(u):
            Cliente.objects.create(razon_social="Juan", tipo="particular")
        self.assertEqual(AuditLog.objects.get().usuario_nombre, "script")

    def test_bitacora_inmutable(self):
        Cliente.objects.create(razon_social="Juan", tipo="particular")
        log = AuditLog.objects.get()
        with self.assertRaises(ValidationError):
            log.save()
        with self.assertRaises(ValidationError):
            log.delete()
