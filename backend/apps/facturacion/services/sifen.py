"""Datos SIFEN de referencia.

El CRM es de uso interno: no emite documentos electrónicos ni se conecta con la
SET. Las facturas las emite el sistema de facturación de la empresa; aquí se
registran sus datos (CDC, timbrado, estado del documento) como referencia para
la cobranza y los reportes.
"""
import re

from apps.clientes.validators import calcular_dv

CDC_RE = re.compile(r"^\d{44}$")


def validar_cdc(cdc: str) -> bool:
    """El CDC tiene 44 dígitos; el último es dígito verificador módulo 11 de los 43 anteriores."""
    return bool(CDC_RE.match(cdc or "")) and calcular_dv(cdc[:43]) == int(cdc[43])
