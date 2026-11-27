from decimal import Decimal

from django.test import SimpleTestCase

from apps.facturacion.services.iva import ErrorIVA, calcular_iva, validar_desglose


class IvaTest(SimpleTestCase):
    def test_precio_con_iva_incluido_se_extrae(self):
        d = calcular_iva(1_100_000, 10, "PYG", precio_incluye_iva=True)
        self.assertEqual((d.base_imponible, d.iva, d.total), (Decimal(1_000_000), Decimal(100_000), Decimal(1_100_000)))

    def test_precio_neto_se_adiciona(self):
        d = calcular_iva(1_000_000, 10, "PYG", precio_incluye_iva=False)
        self.assertEqual(d.total, Decimal(1_100_000))

    def test_guaranies_sin_decimales_y_cuadra(self):
        d = calcular_iva(1_234_567, 10, "PYG", True)
        self.assertEqual(d.iva, Decimal(112_233))  # 1.234.567 / 11 = 112.233,36
        self.assertEqual(d.base_imponible + d.iva, d.total)

    def test_usd_dos_decimales(self):
        d = calcular_iva("123.45", 10, "USD", True)
        self.assertEqual((d.base_imponible, d.iva), (Decimal("112.23"), Decimal("11.22")))

    def test_detecta_iva_sobre_monto_ya_gravado(self):
        # Error típico: tomar 1.100.000 (con IVA) como base y sumarle 10% otra vez.
        with self.assertRaises(ErrorIVA):
            validar_desglose(base=1_000_000, iva=110_000, tasa=10, moneda="PYG")

    def test_tasa_invalida(self):
        with self.assertRaises(ErrorIVA):
            calcular_iva(1000, 12, "PYG", True)
