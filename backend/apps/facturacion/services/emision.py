"""Alta y anulación de facturas (transaccionales)."""
from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Factura, ItemFactura


@transaction.atomic
def crear_factura(datos: dict, items: list[dict], usuario=None) -> Factura:
    if not items:
        raise ValidationError({"items": "La factura debe tener al menos un ítem."})
    factura = Factura(**datos, creado_por=usuario)
    factura.save()
    for it in items:
        ItemFactura(factura=factura, **it).save()
    factura.recalcular_totales()
    factura.validar_limites()
    factura.save()
    if factura.orden_compra_id:
        factura.orden_compra.actualizar_estado()
    return factura


@transaction.atomic
def anular_factura(factura: Factura, motivo: str) -> Factura:
    factura = Factura.objects.select_for_update().get(pk=factura.pk)
    if factura.estado == Factura.Estado.ANULADA:
        raise ValidationError("La factura ya está anulada.")
    if factura.saldo != factura.total:
        raise ValidationError("La factura tiene cobros registrados; revierta los cobros antes de anular.")
    if factura.aprobada_sifen:
        raise ValidationError("El DE está aprobado en SIFEN: registre primero el evento de cancelación "
                              "ante la SET y marque estado_sifen = cancelado.")
    factura.estado = Factura.Estado.ANULADA
    factura.motivo_anulacion = factura.motivo_auditoria = motivo
    factura.saldo = 0
    factura.save()
    if factura.orden_compra_id:
        factura.orden_compra.actualizar_estado()
    return factura
