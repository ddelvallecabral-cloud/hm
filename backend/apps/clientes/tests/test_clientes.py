from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.clientes.validators import calcular_dv, validar_ruc

URL = "/api/clientes/"


class RucTest(TestCase):
    def test_dv_ruc_innominado_set(self):
        self.assertEqual(calcular_dv("44444401"), 7)

    def test_ruc_valido_e_invalido(self):
        validar_ruc("80012345-0")
        with self.assertRaises(ValidationError):
            validar_ruc("80012345-6")
        with self.assertRaises(ValidationError):
            validar_ruc("80012345")


class ClienteModeloTest(TestCase):
    def test_requiere_oc_se_deriva_del_tipo(self):
        casos = {
            Cliente.Tipo.PARTICULAR: False,
            Cliente.Tipo.PROFESIONAL_INDEPENDIENTE: True,
            Cliente.Tipo.PYME: True,
        }
        for i, (tipo, esperado) in enumerate(casos.items()):
            c = Cliente.objects.create(razon_social=f"C{i}", tipo=tipo, ruc=f"{1000000 + i}-{calcular_dv(str(1000000 + i))}")
            self.assertIs(c.requiere_orden_compra, esperado, tipo)

    def test_constraint_bd_plazo_en_contado(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cliente.objects.create(razon_social="X", tipo="particular", condicion_pago="contado", plazo_dias=30)


class ClienteApiTest(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(get_user_model().objects.create_user("tesorero", password="x" * 12))

    def test_requiere_autenticacion(self):
        self.assertEqual(APIClient().get(URL).status_code, 403)

    def test_crear_pyme_credito_y_listar(self):
        r = self.api.post(URL, {
            "ruc": "80012345-0", "razon_social": "Constructora Ñandutí S.A.", "tipo": "pyme",
            "condicion_pago": "credito", "plazo_dias": 60, "limite_credito": "150000000",
            "contacto_cobranza": "María Benítez", "telefono_cobranza": "0981 123456",
            "email_cobranza": "pagos@nandut.com.py",
            # el cliente no puede forzar este campo:
            "requiere_orden_compra": False,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["requiere_orden_compra"])
        lista = self.api.get(URL, {"tipo": "pyme"}).json()
        self.assertEqual(lista["count"], 1)
        self.assertEqual(self.api.get(URL, {"q": "80012345"}).json()["count"], 1)

    def test_particular_contado_sin_ruc(self):
        r = self.api.post(URL, {"razon_social": "Juan Pérez", "tipo": "particular"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.json()["requiere_orden_compra"])
        self.assertIsNone(r.json()["plazo_dias"])

    def test_profesional_sin_ruc_rechazado(self):
        r = self.api.post(URL, {"razon_social": "Arq. Gómez", "tipo": "profesional_independiente"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ruc", r.json())

    def test_credito_requiere_plazo_y_limite(self):
        r = self.api.post(URL, {"razon_social": "Ing. Rojas", "tipo": "profesional_independiente",
                                "ruc": "1234567-9", "condicion_pago": "credito"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("plazo_dias", r.json())
        self.assertIn("limite_credito", r.json())

    def test_plazo_fuera_de_30_60_90(self):
        r = self.api.post(URL, {"razon_social": "Ing. Rojas", "tipo": "profesional_independiente",
                                "ruc": "1234567-9", "condicion_pago": "credito", "plazo_dias": 45,
                                "limite_credito": "1000000"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("plazo_dias", r.json())

    def test_contado_con_plazo_rechazado(self):
        r = self.api.post(URL, {"razon_social": "Juan", "tipo": "particular", "plazo_dias": 30}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_ruc_duplicado(self):
        datos = {"ruc": "80012345-0", "razon_social": "A", "tipo": "pyme"}
        self.assertEqual(self.api.post(URL, datos, format="json").status_code, 201)
        r = self.api.post(URL, {**datos, "razon_social": "B"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ruc", r.json())
