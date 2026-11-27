"""Servicios de cobranza: pagos (total o parcial) de una factura, cobro al contado,
anulación, alertas y cuenta corriente.

Toda operación que mueve saldos corre en una transacción con bloqueo de la
fila de la factura (select_for_update) para no sobrecobrarla cuando dos
usuarios trabajan a la vez.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.facturacion.models import Factura

from .models import GestionCobro, Pago, ParametrosCobranza

CERO = Decimal("0")


def saldo_pendiente(factura: Factura, al=None) -> Decimal:
    """Saldo pendiente de una factura calculado desde sus pagos (ver Factura.calcular_saldo_pendiente)."""
    return factura.calcular_saldo_pendiente(al)


def recalcular_factura(factura: Factura, motivo: str = "") -> Factura:
    factura.saldo = saldo_pendiente(factura)
    factura.actualizar_estado()
    factura.motivo_auditoria = motivo
    factura.save()
    return factura


@transaction.atomic
def registrar_cobranza(factura: Factura, monto, medio: str, fecha=None, usuario=None, **extra) -> Pago:
    """Registra el pago de una factura (contado o crédito).

    - monto < saldo  -> la factura queda "pagada_parcial" (o "vencida_pago_parcial" si ya venció);
    - monto = saldo  -> la factura queda "pagada";
    - monto > saldo  -> se rechaza.
    Bloquea la fila de la factura para que dos usuarios no la cobren a la vez.
    """
    factura = Factura.objects.select_for_update().get(pk=factura.pk)
    if factura.estado in (Factura.Estado.PAGADA, Factura.Estado.ANULADA):
        raise ValidationError(f"La factura ya está {factura.get_estado_display().lower()}.")
    monto = Decimal(monto)
    if monto > factura.saldo:
        raise ValidationError({"monto": f"El monto supera el saldo pendiente ({factura.moneda} {factura.saldo})."})
    moneda = extra.pop("moneda", None) or factura.moneda
    pago = Pago(factura=factura, monto=monto, medio=medio, moneda=moneda, fecha=fecha or timezone.localdate(),
                registrado_por=usuario, **extra)
    pago.full_clean()
    pago.save()
    recalcular_factura(factura, motivo=f"Pago #{pago.pk}")
    return pago


def buscar_facturas_por_cobrar(q: str = "", cliente_id=None, moneda=None, limite: int = 50):
    """Facturas con saldo, buscando por número (001-001-0000123, 0000123 o 123), cliente o RUC."""
    qs = Factura.objects.filter(estado__in=Factura.ESTADOS_ABIERTOS).select_related("cliente")
    if cliente_id:
        qs = qs.filter(cliente_id=cliente_id)
    if moneda:
        qs = qs.filter(moneda=moneda)
    if (q or "").strip():
        from apps.facturacion.views import filtro_busqueda

        qs = qs.filter(filtro_busqueda(q))
    return qs.order_by("fecha_vencimiento", "id")[:limite]


@transaction.atomic
def revisar_gestion(gestion: GestionCobro, usuario, decision: str, mensaje_final="", comentario="") -> GestionCobro:
    gestion.revision = decision
    gestion.mensaje_final = mensaje_final if decision == GestionCobro.Revision.MODIFICADA else gestion.mensaje
    gestion.comentario_revision = comentario
    gestion.revisada_por = usuario
    gestion.revisada_en = timezone.now()
    gestion.motivo_auditoria = f"Revisión de tesorería: {decision}"
    gestion.save()
    return gestion


@transaction.atomic
def registrar_cobro_contado(factura: Factura, medio: str, referencia="", fecha=None, usuario=None, **extra) -> Pago:
    """Cobro inmediato de una factura al contado: crea el pago por el saldo y la deja "pagada"."""
    factura = Factura.objects.select_for_update().get(pk=factura.pk)
    if factura.condicion != Factura.Condicion.CONTADO:
        raise ValidationError("La factura es a crédito: registre el pago con /api/cobranzas/pagos/.")
    return registrar_cobranza(factura, factura.saldo, medio, fecha=fecha, usuario=usuario,
                              referencia=referencia, **extra)


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
    recalcular_factura(Factura.objects.select_for_update().get(pk=pago.factura_id),
                       motivo=f"Anulación del pago #{pago.pk}: {motivo}")
    return pago


def evaluar_promesas(hoy=None) -> int:
    """Marca promesas vencidas como cumplidas o no según los pagos recibidos desde la gestión."""
    hoy = hoy or timezone.localdate()
    n = 0
    pendientes = GestionCobro.objects.filter(resultado=GestionCobro.Resultado.PROMESA_PAGO,
                                             promesa_cumplida__isnull=True, promesa_fecha__lt=hoy)
    for g in pendientes:
        pagado = (Pago.objects.filter(factura__cliente=g.cliente, anulado=False, fecha__gte=timezone.localtime(g.fecha_hora).date(),
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
    """Facturas abiertas, saldo vencido y últimos pagos, por moneda."""
    hoy = hoy or timezone.localdate()
    out = {}
    for moneda in ("PYG", "USD"):
        abiertas = cliente.facturas.filter(moneda=moneda, estado__in=Factura.ESTADOS_ABIERTOS).order_by("fecha_vencimiento")
        pagos = Pago.objects.filter(factura__cliente=cliente, moneda=moneda, anulado=False).select_related("factura")
        if not abiertas.exists() and not pagos.exists():
            continue
        out[moneda] = {
            "saldo_pendiente": sum((f.saldo for f in abiertas), CERO),
            "saldo_vencido": sum((f.saldo for f in abiertas if f.fecha_vencimiento < hoy), CERO),
            "facturas_abiertas": [_fila(f, hoy) for f in abiertas],
            "ultimos_pagos": [{"pago_id": p.pk, "fecha": p.fecha, "factura": p.factura.numero_completo,
                               "monto": p.monto, "medio": p.medio} for p in pagos[:10]],
        }
    return {"cliente_id": cliente.pk, "cliente": cliente.razon_social, "fecha": hoy,
            "limite_credito": cliente.limite_credito, "monedas": out}
