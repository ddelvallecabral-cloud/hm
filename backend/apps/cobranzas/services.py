"""Servicios de cobranza: cobro al contado, pagos parciales, anulación, alertas y cuenta corriente.

Toda operación que mueve saldos corre en una transacción con bloqueo de filas
(select_for_update) para evitar aplicar dos veces el mismo pago o sobrecobrar
una factura cuando dos usuarios trabajan a la vez.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.facturacion.models import Factura

from .models import AplicacionPago, GestionCobro, Pago, ParametrosCobranza

CERO = Decimal("0")


def recalcular_factura(factura: Factura, motivo: str = "") -> Factura:
    cobrado = (factura.aplicaciones.filter(pago__anulado=False).aggregate(s=Sum("monto"))["s"] or CERO)
    factura.saldo = max(factura.total - cobrado, CERO)
    factura.actualizar_estado()
    factura.motivo_auditoria = motivo
    factura.save()
    return factura


@transaction.atomic
def aplicar_pago(pago: Pago, imputaciones: list[dict]) -> list[AplicacionPago]:
    """Aplica un pago a facturas: imputaciones = [{"factura": Factura, "monto": Decimal}, ...]."""
    pago = Pago.objects.select_for_update().get(pk=pago.pk)
    if pago.anulado:
        raise ValidationError("No se puede aplicar un pago anulado.")
    disponible = pago.monto_sin_aplicar
    creadas = []
    for imp in imputaciones:
        f = Factura.objects.select_for_update().get(pk=imp["factura"].pk)
        monto = Decimal(imp["monto"])
        if f.estado in (Factura.Estado.ANULADA, Factura.Estado.PAGADA):
            raise ValidationError(f"La factura {f.numero_completo} está {f.get_estado_display().lower()}.")
        if monto <= 0:
            raise ValidationError("El monto a aplicar debe ser mayor a 0.")
        if monto > f.saldo:
            raise ValidationError(f"El monto {monto} supera el saldo de la factura {f.numero_completo} ({f.saldo}).")
        if monto > disponible:
            raise ValidationError(f"El pago no tiene saldo suficiente: disponible {disponible}.")
        a = AplicacionPago(pago=pago, factura=f, monto=monto)
        a.full_clean()
        a.save()
        disponible -= monto
        creadas.append(a)
        recalcular_factura(f, motivo=f"Aplicación del pago #{pago.pk}")
    return creadas


def imputacion_automatica(cliente, moneda: str, monto: Decimal) -> list[dict]:
    """Reparte un monto entre las facturas abiertas del cliente, empezando por la de vencimiento más antiguo."""
    restante, imputaciones = Decimal(monto), []
    abiertas = (Factura.objects.filter(cliente=cliente, moneda=moneda, estado__in=Factura.ESTADOS_ABIERTOS)
                .order_by("fecha_vencimiento", "id"))
    for f in abiertas:
        if restante <= 0:
            break
        m = min(restante, f.saldo)
        imputaciones.append({"factura": f, "monto": m})
        restante -= m
    return imputaciones


@transaction.atomic
def registrar_pago(datos: dict, imputaciones=None, automatico=False, usuario=None) -> Pago:
    """Registra un pago (total o parcial). Sin imputaciones y sin `automatico`, queda como saldo a favor."""
    pago = Pago(**datos, registrado_por=usuario)
    pago.full_clean()
    pago.save()
    if automatico:
        imputaciones = imputacion_automatica(pago.cliente, pago.moneda, pago.monto)
    if imputaciones:
        aplicar_pago(pago, imputaciones)
    return pago


@transaction.atomic
def registrar_cobro_contado(factura: Factura, medio: str, referencia="", fecha=None, usuario=None, **extra) -> Pago:
    """Cobro inmediato de una factura al contado: crea el pago por el saldo y la deja "pagada"."""
    factura = Factura.objects.select_for_update().get(pk=factura.pk)
    if factura.condicion != Factura.Condicion.CONTADO:
        raise ValidationError("La factura es a crédito: registre el pago con /api/cobranzas/pagos/.")
    if factura.estado in (Factura.Estado.PAGADA, Factura.Estado.ANULADA):
        raise ValidationError(f"La factura ya está {factura.get_estado_display().lower()}.")
    return registrar_pago(
        {"cliente": factura.cliente, "fecha": fecha or timezone.localdate(), "moneda": factura.moneda,
         "monto": factura.saldo, "medio": medio, "referencia": referencia, **extra},
        imputaciones=[{"factura": factura, "monto": factura.saldo}], usuario=usuario,
    )


@transaction.atomic
def anular_pago(pago: Pago, motivo: str) -> Pago:
    pago = Pago.objects.select_for_update().get(pk=pago.pk)
    if pago.anulado:
        raise ValidationError("El pago ya está anulado.")
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la anulación."})
    pago.anulado = True
    pago.motivo_anulacion = pago.motivo_auditoria = motivo
    pago.full_clean()
    pago.save()
    for a in pago.aplicaciones.select_related("factura"):
        recalcular_factura(a.factura, motivo=f"Anulación del pago #{pago.pk}: {motivo}")
    return pago


def evaluar_promesas(hoy=None) -> int:
    """Marca promesas vencidas como cumplidas o no según los pagos recibidos desde la gestión."""
    hoy = hoy or timezone.localdate()
    n = 0
    pendientes = GestionCobro.objects.filter(resultado=GestionCobro.Resultado.PROMESA_PAGO,
                                             promesa_cumplida__isnull=True, promesa_fecha__lt=hoy)
    for g in pendientes:
        pagado = (Pago.objects.filter(cliente=g.cliente, anulado=False, fecha__gte=timezone.localtime(g.fecha_hora).date(),
                                      fecha__lte=g.promesa_fecha).aggregate(s=Sum("monto"))["s"] or CERO)
        g.promesa_cumplida = pagado >= g.promesa_monto
        g.motivo_auditoria = "Evaluación automática de promesa"
        g.save(update_fields=["promesa_cumplida"])
        n += 1
    return n


def _fila(f: Factura, hoy):
    return {"factura_id": f.pk, "numero": f.numero_completo, "cliente_id": f.cliente_id,
            "cliente": f.cliente.razon_social, "moneda": f.moneda, "total": f.total, "saldo": f.saldo,
            "fecha_vencimiento": f.fecha_vencimiento, "estado": f.estado,
            "dias": (f.fecha_vencimiento - hoy).days}


def alertas_vencimiento(hoy=None, dias=None) -> dict:
    """Facturas que vencen en los próximos `dias` y facturas ya vencidas (días de atraso en negativo)."""
    hoy = hoy or timezone.localdate()
    dias = ParametrosCobranza.get().dias_aviso_vencimiento if dias is None else dias
    abiertas = Factura.objects.filter(estado__in=Factura.ESTADOS_ABIERTOS).select_related("cliente")
    return {
        "fecha": hoy,
        "proximas_a_vencer": [_fila(f, hoy) for f in abiertas.filter(
            fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=hoy + timedelta(days=dias)).order_by("fecha_vencimiento")],
        "vencidas": [{**_fila(f, hoy), "dias_atraso": (hoy - f.fecha_vencimiento).days}
                     for f in abiertas.filter(fecha_vencimiento__lt=hoy).order_by("fecha_vencimiento")],
    }


def cuenta_corriente(cliente, hoy=None) -> dict:
    """Facturas abiertas, últimos pagos y saldo a favor, por moneda."""
    hoy = hoy or timezone.localdate()
    out = {}
    for moneda in ("PYG", "USD"):
        abiertas = cliente.facturas.filter(moneda=moneda, estado__in=Factura.ESTADOS_ABIERTOS).order_by("fecha_vencimiento")
        pagos = cliente.pagos.filter(moneda=moneda, anulado=False)
        if not abiertas.exists() and not pagos.exists():
            continue
        out[moneda] = {
            "saldo_pendiente": sum((f.saldo for f in abiertas), CERO),
            "saldo_vencido": sum((f.saldo for f in abiertas if f.fecha_vencimiento < hoy), CERO),
            "saldo_a_favor": sum((p.monto_sin_aplicar for p in pagos), CERO),
            "facturas_abiertas": [_fila(f, hoy) for f in abiertas],
            "ultimos_pagos": [{"pago_id": p.pk, "fecha": p.fecha, "monto": p.monto, "medio": p.medio,
                               "sin_aplicar": p.monto_sin_aplicar} for p in pagos[:10]],
        }
    return {"cliente_id": cliente.pk, "cliente": cliente.razon_social, "fecha": hoy,
            "limite_credito": cliente.limite_credito, "monedas": out}
