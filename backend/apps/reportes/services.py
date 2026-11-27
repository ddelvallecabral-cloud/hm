"""Reportes: estado de cuenta por cliente, IVA débito fiscal por período y OC pendientes de conciliación."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from apps.cobranzas.models import Pago
from apps.facturacion.models import Factura, OrdenCompra
from apps.tesoreria.services import facturas_pendientes

CERO = Decimal("0")


def _gs(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal(1), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
def estado_cuenta(cliente, desde: date, hasta: date) -> dict:
    """Movimientos del cliente por moneda: saldo inicial, facturas (debe), pagos (haber) y saldo final.

    No incluye facturas anuladas ni pagos anulados. Agrega las facturas con saldo
    a la fecha `hasta`, con su interés por mora a esa fecha (informativo).
    """
    facturas = Factura.objects.filter(cliente=cliente).exclude(estado=Factura.Estado.ANULADA)
    pagos = Pago.objects.filter(factura__cliente=cliente, anulado=False).select_related("factura")
    monedas = {}
    for moneda in ("PYG", "USD"):
        fm, pm = facturas.filter(moneda=moneda), pagos.filter(moneda=moneda)
        inicial = ((fm.filter(fecha_emision__lt=desde).aggregate(s=Sum("total"))["s"] or CERO)
                   - (pm.filter(fecha__lt=desde).aggregate(s=Sum("monto"))["s"] or CERO))
        movs = [{"fecha": f.fecha_emision, "tipo": "Factura", "documento": f.numero_completo,
                 "detalle": f"{f.get_condicion_display()}{' · OC ' + f.orden_compra.numero if f.orden_compra_id else ''}"
                            f" · vence {f.fecha_vencimiento:%d/%m/%Y}",
                 "debe": f.total, "haber": CERO, "orden": 0}
                for f in fm.filter(fecha_emision__range=(desde, hasta)).select_related("orden_compra")]
        movs += [{"fecha": p.fecha, "tipo": "Pago", "documento": p.factura.numero_completo,
                  "detalle": f"{p.get_medio_display()}{' · ' + p.referencia if p.referencia else ''}"
                             f"{' · recibo ' + p.numero_recibo if p.numero_recibo else ''}",
                  "debe": CERO, "haber": p.monto, "orden": 1}
                 for p in pm.filter(fecha__range=(desde, hasta))]
        if not movs and not inicial:
            continue
        movs.sort(key=lambda x: (x["fecha"], x["orden"]))
        saldo = inicial
        for m in movs:
            saldo += m["debe"] - m["haber"]
            m["saldo"] = saldo
            del m["orden"]
        monedas[moneda] = {
            "saldo_inicial": inicial, "movimientos": movs,
            "total_debe": sum((m["debe"] for m in movs), CERO), "total_haber": sum((m["haber"] for m in movs), CERO),
            "saldo_final": saldo,
        }
    pendientes = facturas_pendientes(hasta, cliente_id=cliente.pk)
    return {
        "cliente": {"id": cliente.pk, "razon_social": cliente.razon_social, "ruc": cliente.ruc,
                    "tipo": cliente.get_tipo_display(), "condicion_pago": cliente.get_condicion_pago_display(),
                    "plazo_dias": cliente.plazo_dias, "limite_credito": cliente.limite_credito,
                    "contacto": cliente.contacto_cobranza, "email": cliente.email_cobranza,
                    "telefono": cliente.telefono_cobranza},
        "desde": desde, "hasta": hasta, "monedas": monedas,
        "facturas_pendientes": pendientes,
        "interes_mora_total": {m: sum((f["interes_mora"] for f in pendientes if f["moneda"] == m), CERO)
                               for m in ("PYG", "USD")},
    }


# --------------------------------------------------------------------------- #
def iva_periodo(anio: int, mes: int) -> dict:
    """IVA débito fiscal del mes (insumo para el Formulario 120 de IVA de la SET).

    Incluye las facturas emitidas en el mes, no anuladas. Las rechazadas o
    canceladas en SIFEN se listan aparte y no suman. Las facturas en USD se
    convierten a guaraníes con el tipo de cambio registrado en cada factura
    (confirmar con el contador el tipo de cambio que exige la SET).
    """
    desde = date(anio, mes, 1)
    hasta = date(anio, mes, monthrange(anio, mes)[1])
    qs = (Factura.objects.filter(fecha_emision__range=(desde, hasta)).exclude(estado=Factura.Estado.ANULADA)
          .select_related("cliente").order_by("fecha_emision", "establecimiento", "punto_expedicion", "numero"))
    detalle, excluidas = [], []
    tot = {"base_imponible": CERO, "iva": CERO, "total": CERO, "retencion_iva": CERO}
    por_moneda = {m: {"cantidad": 0, "base_imponible": CERO, "iva": CERO, "total": CERO} for m in ("PYG", "USD")}
    for f in qs:
        fila = {"fecha": f.fecha_emision, "numero": f.numero_completo, "timbrado": f.timbrado, "cdc": f.cdc,
                "estado_sifen": f.estado_sifen, "cliente": f.cliente.razon_social, "ruc": f.cliente.ruc,
                "condicion": f.condicion, "moneda": f.moneda, "tipo_cambio": f.tipo_cambio,
                "base_imponible": f.base_imponible, "iva": f.iva, "total": f.total, "retencion_iva": f.retencion_iva}
        if f.estado_sifen in (Factura.EstadoSifen.RECHAZADO, Factura.EstadoSifen.CANCELADO):
            excluidas.append(fila)
            continue
        tc = f.tipo_cambio if f.moneda == "USD" else Decimal(1)
        for k in tot:
            fila[f"{k}_gs"] = _gs(getattr(f, k) * tc)
            tot[k] += fila[f"{k}_gs"]
        pm = por_moneda[f.moneda]
        pm["cantidad"] += 1
        for k in ("base_imponible", "iva", "total"):
            pm[k] += getattr(f, k)
        detalle.append(fila)
    return {
        "periodo": f"{mes:02d}/{anio}", "desde": desde, "hasta": hasta,
        "cantidad_facturas": len(detalle),
        "totales_gs": {**tot, "debito_fiscal": tot["iva"]},
        "por_moneda": por_moneda,
        "facturas": detalle,
        "excluidas_sifen": excluidas,
        "sin_aprobacion_sifen": sum(1 for f in detalle if f["estado_sifen"] not in ("aprobado", "aprobado_obs")),
    }


# --------------------------------------------------------------------------- #
def oc_pendientes(cliente_id=None) -> dict:
    """Facturas con OC cuyo cobro no está conciliado (saldo pendiente) y OC con monto aún sin facturar."""
    facturas = (Factura.objects.filter(orden_compra__isnull=False, estado__in=Factura.ESTADOS_ABIERTOS)
                .select_related("orden_compra", "cliente").order_by("fecha_vencimiento"))
    ocs = (OrdenCompra.objects.exclude(estado=OrdenCompra.Estado.ANULADA)
           .select_related("cliente").order_by("fecha"))
    if cliente_id:
        facturas, ocs = facturas.filter(cliente_id=cliente_id), ocs.filter(cliente_id=cliente_id)
    hoy = date.today()
    filas_f = [{"oc": f.orden_compra.numero, "obra": f.orden_compra.obra_proyecto, "factura": f.numero_completo,
                "factura_id": f.pk, "cliente": f.cliente.razon_social, "moneda": f.moneda,
                "fecha_emision": f.fecha_emision, "fecha_vencimiento": f.fecha_vencimiento,
                "total": f.total, "cobrado": f.total - f.saldo, "saldo": f.saldo, "estado": f.estado,
                "dias_atraso": max((hoy - f.fecha_vencimiento).days, 0)} for f in facturas]
    filas_oc = []
    for o in ocs:
        facturado = o.monto_facturado
        if facturado < o.monto_total:
            filas_oc.append({"oc": o.numero, "cliente": o.cliente.razon_social, "obra": o.obra_proyecto,
                             "fecha": o.fecha, "moneda": o.moneda, "monto_oc": o.monto_total,
                             "facturado": facturado, "pendiente_de_facturar": o.monto_total - facturado,
                             "estado": o.estado})
    return {
        "facturas_con_saldo": filas_f,
        "totales_facturas": {m: sum((f["saldo"] for f in filas_f if f["moneda"] == m), CERO) for m in ("PYG", "USD")},
        "ordenes_pendientes_de_facturar": filas_oc,
    }
