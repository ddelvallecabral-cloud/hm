from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.clientes.validators import calcular_dv
from apps.core.models import AuditLog
from apps.facturacion.models import Factura, OrdenCompra

URL = "/api/facturacion/facturas/"
VARILLA = {"descripcion": "Varilla conformada 12 mm x 12 m", "unidad": "BARRA", "cantidad": "100",
           "precio_unitario": "110000"}  # 11.000.000 Gs. IVA incluido


def cdc_valido():
    base = "01800123450001001000000122026112711234567890"[:43]
    return base + str(calcular_dv(base))


class FacturaApiBase(TestCase):
    def setUp(self):
        u = get_user_model().objects.create_user("tes", password="x" * 12, rol="tesorero")
        self.api = APIClient()
        self.api.force_authenticate(u)
        self.particular = Cliente.objects.create(razon_social="Juan Pérez", tipo="particular")
        self.pyme = Cliente.objects.create(ruc="80012345-0", razon_social="Constructora Ñandutí", tipo="pyme",
                                           condicion_pago="credito", plazo_dias=60, limite_credito=30_000_000)
        self.oc = OrdenCompra.objects.create(cliente=self.pyme, numero="OC-778", fecha=date(2026, 11, 20),
                                             monto_total=25_000_000)
        self.n = 0

    def factura(self, cliente, items=None, **extra):
        self.n += 1
        datos = {"cliente": cliente.pk, "timbrado": "12345678", "establecimiento": "001",
                 "punto_expedicion": "001", "numero": f"{self.n:07d}", "fecha_emision": "2026-11-27",
                 "condicion": "contado", "items": items or [VARILLA], **extra}
        return self.api.post(URL, datos, format="json")


class FacturaTest(FacturaApiBase):
    def test_particular_contado_sin_oc_desglosa_iva(self):
        r = self.factura(self.particular)
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["gravada_10"], d["iva_10"], d["total"]), ("10000000.00", "1000000.00", "11000000.00"))
        self.assertEqual(d["fecha_vencimiento"], "2026-11-27")
        self.assertFalse(d["requiere_orden_compra"])

    def test_particular_no_admite_oc(self):
        r = self.factura(self.particular, orden_compra=self.oc.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn("orden_compra", r.json())

    def test_pyme_exige_oc(self):
        r = self.factura(self.pyme, condicion="credito", plazo_dias=60)
        self.assertEqual(r.status_code, 400)
        self.assertIn("orden_compra", r.json())

    def test_pyme_credito_vencimiento_automatico_y_estado_oc(self):
        r = self.factura(self.pyme, condicion="credito", plazo_dias=60, orden_compra=self.oc.pk)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["fecha_vencimiento"], "2027-01-26")
        self.oc.refresh_from_db()
        self.assertEqual(self.oc.estado, "parcial")

    def test_plazo_mayor_al_pactado(self):
        r = self.factura(self.pyme, condicion="credito", plazo_dias=90, orden_compra=self.oc.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn("plazo_dias", r.json())

    def test_particular_sin_credito_no_factura_a_credito(self):
        r = self.factura(self.particular, condicion="credito", plazo_dias=30)
        self.assertEqual(r.status_code, 400)
        self.assertIn("condicion", r.json())

    def test_limite_de_credito(self):
        oc2 = OrdenCompra.objects.create(cliente=self.pyme, numero="OC-779", fecha=date(2026, 11, 20),
                                         monto_total=50_000_000)
        self.assertEqual(self.factura(self.pyme, condicion="credito", plazo_dias=30, orden_compra=oc2.pk,
                                      items=[{**VARILLA, "cantidad": "200"}]).status_code, 201)  # 22M
        r = self.factura(self.pyme, condicion="credito", plazo_dias=30, orden_compra=oc2.pk)  # +11M > 30M
        self.assertEqual(r.status_code, 400)
        self.assertIn("límite de crédito", r.json()["total"][0])
        self.assertEqual(Factura.objects.count(), 1)  # la transacción revirtió la factura rechazada

    def test_factura_no_supera_saldo_de_oc(self):
        r = self.factura(self.pyme, orden_compra=self.oc.pk, items=[{**VARILLA, "cantidad": "300"}])  # 33M > 25M
        self.assertEqual(r.status_code, 400)
        self.assertIn("orden_compra", r.json())

    def test_usd_requiere_tipo_cambio_y_convierte_para_limite(self):
        oc_usd = OrdenCompra.objects.create(cliente=self.pyme, numero="OC-USD", fecha=date(2026, 11, 20),
                                            moneda="USD", monto_total=10_000)
        item = {"descripcion": "Chapa", "cantidad": "1", "precio_unitario": "3300"}
        r = self.factura(self.pyme, moneda="USD", orden_compra=oc_usd.pk, items=[item])
        self.assertEqual(r.status_code, 400)
        self.assertIn("tipo_cambio", r.json())
        r = self.factura(self.pyme, moneda="USD", tipo_cambio="7800", orden_compra=oc_usd.pk, items=[item])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["gravada_10"], r.json()["iva_10"]), ("3000.00", "300.00"))

    def test_item_con_precio_neto(self):
        r = self.factura(self.particular, items=[{**VARILLA, "precio_unitario": "100000", "precio_incluye_iva": False}])
        self.assertEqual(r.json()["total"], "11000000.00")

    def test_retencion_iva(self):
        r = self.factura(self.pyme, orden_compra=self.oc.pk, porcentaje_retencion_iva="30")
        self.assertEqual(r.json()["retencion_iva"], "300000.00")


class FacturaPostEmisionTest(FacturaApiBase):
    def setUp(self):
        super().setUp()
        self.fid = self.factura(self.particular).json()["id"]

    def test_cdc_invalido(self):
        r = self.api.patch(f"{URL}{self.fid}/", {"cdc": "1" * 44}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_aprobar_en_sifen_y_bloquear_anulacion(self):
        r = self.api.patch(f"{URL}{self.fid}/", {"cdc": cdc_valido(), "estado_sifen": "aprobado"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = self.api.post(f"{URL}{self.fid}/anular/", {"motivo": "error de carga"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("SIFEN", str(r.json()))

    def test_prorroga_requiere_motivo_y_queda_auditada(self):
        self.assertEqual(self.api.patch(f"{URL}{self.fid}/", {"fecha_vencimiento": "2026-12-15"},
                                        format="json").status_code, 400)
        r = self.api.patch(f"{URL}{self.fid}/", {"fecha_vencimiento": "2026-12-15", "motivo": "Prórroga acordada"},
                           format="json")
        self.assertEqual(r.status_code, 200, r.content)
        log = AuditLog.objects.filter(modelo="facturacion.Factura", objeto_id=str(self.fid)).latest("id")
        self.assertEqual(log.cambios["fecha_vencimiento"], ["2026-11-27", "2026-12-15"])
        self.assertEqual(log.motivo, "Prórroga acordada")
        self.assertEqual(log.usuario.username, "tes")

    def test_anular(self):
        self.assertEqual(self.api.post(f"{URL}{self.fid}/anular/", {}, format="json").status_code, 400)
        r = self.api.post(f"{URL}{self.fid}/anular/", {"motivo": "Cliente desistió"}, format="json")
        self.assertEqual(r.json()["estado"], "anulada")

    def test_cobrador_no_puede_anular(self):
        u = get_user_model().objects.create_user("cob", password="x" * 12, rol="cobrador")
        api = APIClient()
        api.force_authenticate(u)
        self.assertEqual(api.post(f"{URL}{self.fid}/anular/", {"motivo": "x"}, format="json").status_code, 403)
