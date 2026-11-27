"""Cálculo del IVA 10% (Ley N° 6380/2019, tasa general aplicable a hierros
y productos siderúrgicos).

Regla de exactitud: el IVA es SIEMPRE exactamente el 10% de la base
imponible, redondeado a la unidad mínima de la moneda:

    iva = redondear(base × 10 / 100)      (PYG: 0 decimales, USD: 2; HALF_UP)

Cómo se obtiene la base según cómo se expresó el precio:
  * Precio con IVA incluido (lo habitual en Paraguay):
        base = redondear(total × 100 / 110);   iva = redondear(base × 10%)
    El IVA se EXTRAE del precio; nunca se vuelve a sumar sobre un monto que ya
    lo contiene. Es la misma secuencia que usa el Manual Técnico SIFEN
    (base gravada a partir del total del ítem, y liquidación del IVA sobre esa
    base); confirmar con el proveedor del facturador electrónico.
    Por el redondeo a guaraníes enteros, base + iva puede diferir del total en
    1 unidad mínima (p. ej. total Gs. 5 → base 5, IVA 0). El total es siempre el
    precio cobrado; esa diferencia se informa en `diferencia_redondeo`.
  * Precio neto (sin IVA):
        base = precio;  iva = redondear(base × 10%);  total = base + iva   (siempre cuadra)
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TASA_IVA = Decimal("10")
DECIMALES = {"PYG": 0, "USD": 2}


class ErrorIVA(ValueError):
    pass


def unidad_minima(moneda: str) -> Decimal:
    return Decimal(1).scaleb(-DECIMALES[moneda])


def redondear(monto, moneda: str) -> Decimal:
    return Decimal(str(monto)).quantize(unidad_minima(moneda), rounding=ROUND_HALF_UP)


def iva_de_base(base, moneda: str) -> Decimal:
    return redondear(Decimal(str(base)) * TASA_IVA / 100, moneda)


@dataclass(frozen=True)
class DesgloseIVA:
    base_imponible: Decimal
    iva: Decimal
    total: Decimal

    @property
    def diferencia_redondeo(self) -> Decimal:
        return self.total - self.base_imponible - self.iva


def calcular_iva(monto, moneda: str, precio_incluye_iva: bool = True) -> DesgloseIVA:
    monto = Decimal(str(monto))
    if monto < 0:
        raise ErrorIVA("El monto no puede ser negativo; las devoluciones van en nota de crédito.")
    if precio_incluye_iva:
        total = redondear(monto, moneda)
        base = redondear(total * 100 / (100 + TASA_IVA), moneda)
    else:
        base = redondear(monto, moneda)
        total = None
    iva = iva_de_base(base, moneda)
    return DesgloseIVA(base, iva, total if total is not None else base + iva)


def validar_iva(base, iva, total, moneda: str) -> None:
    """IVA exactamente 10% de la base y total coherente (±1 unidad mínima de redondeo)."""
    base, iva, total = Decimal(base), Decimal(iva), Decimal(total)
    esperado = iva_de_base(base, moneda)
    if iva != esperado:
        raise ErrorIVA(
            f"El IVA debe ser exactamente el 10% de la base: base {base} → IVA {esperado}, informado {iva}. "
            "Si el precio ya incluía IVA, no se le debe volver a aplicar."
        )
    if abs(total - base - iva) > unidad_minima(moneda):
        raise ErrorIVA(f"El total {total} no corresponde a base {base} + IVA {iva}.")
