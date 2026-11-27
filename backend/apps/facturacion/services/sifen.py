"""Datos SIFEN (Sistema Integrado de Facturación Electrónica Nacional, SET).

En esta etapa el CRM REGISTRA los datos del Documento Electrónico (DE) que
emite el sistema facturador: CDC, timbrado, estado del DTE, KuDE. No genera ni
firma XML ni llama a los web services de la SET.

Configuración adicional necesaria para una integración real:
  1. Habilitación como facturador electrónico y timbrado electrónico vigente.
  2. Certificado digital de persona jurídica (PSC habilitado) y CSC entregado
     por la SET (variables SIFEN_* en .env).
  3. Armado del XML según el Manual Técnico SIFEN vigente, firma XMLDSig, QR y
     envío a los servicios de recepción/consulta/eventos de la SET.
Se recomienda delegarlo en un proveedor o librería homologada que implemente
`ClienteSIFEN`.
"""
import re

from apps.clientes.validators import calcular_dv

CDC_RE = re.compile(r"^\d{44}$")


def validar_cdc(cdc: str) -> bool:
    """El CDC tiene 44 dígitos; el último es dígito verificador módulo 11 de los 43 anteriores."""
    return bool(CDC_RE.match(cdc or "")) and calcular_dv(cdc[:43]) == int(cdc[43])


class ClienteSIFEN:
    """Interfaz para el futuro conector con la SET."""

    def enviar(self, factura) -> dict:  # pragma: no cover
        raise NotImplementedError("Integración SIFEN no configurada.")

    def consultar(self, cdc: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def cancelar(self, cdc: str, motivo: str) -> dict:  # pragma: no cover
        raise NotImplementedError
