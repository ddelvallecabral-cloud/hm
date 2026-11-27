from decimal import Decimal

from django.test import SimpleTestCase

from apps.facturacion.services.iva import ErrorIVA, calcular_iva, iva_de_base, validar_iva


class IvaTest(SimpleTestCase):
    def test_precio_con_iva_incluido_se_extrae(self):
        d = calcular_iva(1_100_000, "PYG", precio_incluye_iva=True)
        self.assertEqual((d.base_imponible, d.iva, d.total), (Decimal(1_000_000), Decimal(100_000), Decimal(1_100_000)))

    def test_precio_neto_se_suma(self):
        d = calcular_iva(1_000_000, "PYG", precio_incluye_iva=False)
        self.assertEqual((d.base_imponible, d.iva, d.total), (Decimal(1_000_000), Decimal(100_000), Decimal(1_100_000)))

    def test_iva_siempre_10_exacto_de_la_base(self):
        # Recorre muchos totales en guaraníes y en dólares: el IVA debe ser siempre round(base × 10%).
        for total in list(range(1, 3000)) + [1_234_567, 9_999_999, 87_654_321]:
            for moneda, monto in (("PYG", total), ("USD", Decimal(total) / 100)):
                d = calcular_iva(monto, moneda, True)
                self.assertEqual(d.iva, iva_de_base(d.base_imponible, moneda), (moneda, monto))
                self.assertLessEqual(abs(d.diferencia_redondeo), Decimal(1) if moneda == "PYG" else Decimal("0.01"))

    def test_usd_dos_decimales(self):
        d = calcular_iva("123.45", "USD", True)
        self.assertEqual((d.base_imponible, d.iva, d.total), (Decimal("112.23"), Decimal("11.22"), Decimal("123.45")))

    def test_rechaza_iva_que_no_es_10_por_ciento(self):
        with self.assertRaises(ErrorIVA):
            validar_iva(base=1_000_000, iva=110_000, total=1_110_000, moneda="PYG")  # IVA sobre monto ya gravado
        with self.assertRaises(ErrorIVA):
            validar_iva(base=1_000_000, iva=50_000, total=1_050_000, moneda="PYG")  # tasa 5%

    def test_rechaza_total_incoherente(self):
        with self.assertRaises(ErrorIVA):
            validar_iva(base=1_000_000, iva=100_000, total=1_200_000, moneda="PYG")

    def test_monto_negativo(self):
        with self.assertRaises(ErrorIVA):
            calcular_iva(-1, "PYG")
