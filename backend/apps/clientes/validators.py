"""Validación del RUC paraguayo.

Formato: número base (hasta 8 dígitos) + guion + dígito verificador (DV).
El DV se calcula con el algoritmo módulo 11 de la SET: factores 2, 3, 4…
aplicados de derecha a izquierda; si el resto es 0 o 1, el DV es 0.
"""
import re

from django.core.exceptions import ValidationError

RUC_RE = re.compile(r"^(\d{1,8})-(\d)$")


def calcular_dv(numero: str, base_max: int = 11) -> int:
    total, factor = 0, 2
    for digito in reversed(numero):
        if factor > base_max:
            factor = 2
        total += int(digito) * factor
        factor += 1
    resto = total % 11
    return 11 - resto if resto > 1 else 0


def validar_ruc(valor: str) -> None:
    m = RUC_RE.match(valor or "")
    if not m:
        raise ValidationError("Formato de RUC inválido. Use número-DV, p. ej. 80012345-0.")
    numero, dv = m.groups()
    esperado = calcular_dv(numero)
    if esperado != int(dv):
        raise ValidationError(f"Dígito verificador de RUC incorrecto (para {numero} corresponde {esperado}).")
