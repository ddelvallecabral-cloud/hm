"""Cálculo de IVA (Ley N° 6380/2019).

Tasas vigentes: 10% (general; aplica a hierros y productos siderúrgicos),
5% (bienes puntuales) y exento. Se admiten las tres para no forzar errores si
algún ítem tiene otro tratamiento, pero el valor por defecto es 10%.

Regla "el IVA nunca se aplica sobre montos ya gravados":
En Paraguay los precios se expresan con IVA incluido. Cada ítem declara
explícitamente `precio_incluye_iva`:
  - True  -> el IVA se EXTRAE del precio:  IVA = total × 10/110  (= total / 11)
  - False -> el IVA se ADICIONA a la base:  IVA = base × 10%
Así el sistema nunca multiplica por 1,10 un precio que ya contiene el impuesto.
`validar_desglose()` vuelve a comprobar el resultado (base + IVA = total y
IVA = base × tasa) antes de guardar la factura.

Redondeo: PYG a 0 decimales, USD a 2, HALF_UP, una única vez por ítem.
La base se obtiene por diferencia (total − IVA) para que siempre cuadre.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TASAS_IVA_VALIDAS = (Decimal("0"), Decimal("5"), Decimal("10"))
DECIMALES = {"PYG": 0, "USD": 2}


class ErrorIVA(ValueError):
    pass


def redondear(monto, moneda: str) -> Decimal:
    return Decimal(monto).quantize(Decimal(1).scaleb(-DECIMALES[moneda]), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DesgloseIVA:
    base_imponible: Decimal
    iva: Decimal
    total: Decimal


def calcular_iva(monto, tasa, moneda: str, precio_incluye_iva: bool) -> DesgloseIVA:
    monto, tasa = Decimal(str(monto)), Decimal(str(tasa))
    if tasa not in TASAS_IVA_VALIDAS:
        raise ErrorIVA(f"Tasa de IVA {tasa}% no válida (0, 5 o 10).")
    if monto < 0:
        raise ErrorIVA("El monto no puede ser negativo; las devoluciones van en nota de crédito.")
    if tasa == 0:
        m = redondear(monto, moneda)
        return DesgloseIVA(m, Decimal(0), m)
    if precio_incluye_iva:
        total = redondear(monto, moneda)
        iva = redondear(total * tasa / (100 + tasa), moneda)
        return DesgloseIVA(total - iva, iva, total)
    base = redondear(monto, moneda)
    iva = redondear(base * tasa / 100, moneda)
    return DesgloseIVA(base, iva, base + iva)


def validar_desglose(base, iva, tasa, moneda: str, lineas: int = 1) -> None:
    """Comprueba que el IVA corresponda a la base (tolerancia: 1 unidad mínima por línea redondeada).

    Detecta el error típico de aplicar IVA a un precio que ya lo incluía
    (en ese caso el IVA queda ~10% más alto que base × tasa).
    """
    base, iva, tasa = Decimal(base), Decimal(iva), Decimal(tasa)
    if tasa == 0:
        if iva:
            raise ErrorIVA("Un monto exento no puede tener IVA.")
        return
    esperado = base * tasa / 100
    tolerancia = Decimal(1).scaleb(-DECIMALES[moneda]) * max(lineas, 1)
    if abs(iva - esperado) > tolerancia:
        raise ErrorIVA(
            f"IVA {tasa}% inconsistente: base {base} → se esperaba {redondear(esperado, moneda)}, hay {iva}. "
            "¿Se aplicó IVA sobre un precio que ya lo incluía?"
        )
