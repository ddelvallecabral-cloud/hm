"""Dashboard de tesorería: cartera por aging, interés por mora, totales por moneda y DSO.

Los importes NUNCA se mezclan entre monedas: todo se informa por separado en PYG y USD.
"""
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.facturacion.models import Factura
from apps.intereses.services import ErrorTasaNoCargada, calcular_interes_moratorio

CERO = Decimal("0")
MONEDAS = ("PYG", "USD")
RANGOS = [  # (clave, título, desde días de atraso, hasta)
    ("corriente", "Corriente (no vencidas)", None, 0),
    ("1-30", "1 a 30 días", 1, 30),
    ("31-60", "31 a 60 días", 31, 60),
    ("61-90", "61 a 90 días", 61, 90),
    ("90+", "Más de 90 días", 91, None),
]


def rango_de(dias: int) -> str:
    for clave, _, desde, hasta in RANGOS:
        if (desde is None or dias >= desde) and (hasta is None or dias <= hasta):
            return clave
    return "90+"


def facturas_pendientes(fecha: date, moneda=None, cliente_id=None) -> list[dict]:
    """Facturas con saldo a la fecha de corte, con días de atraso, rango e interés por mora acumulado."""
    qs = (Factura.objects.exclude(estado=Factura.Estado.ANULADA).filter(fecha_emision__lte=fecha)
          .select_related("cliente").order_by("fecha_vencimiento", "id"))
    if moneda:
        qs = qs.filter(moneda=moneda)
    if cliente_id:
        qs = qs.filter(cliente_id=cliente_id)
    hoy = timezone.localdate()
    filas = []
    for f in qs:
        saldo = f.saldo if fecha >= hoy else f.calcular_saldo_pendiente(fecha)
        if saldo <= 0:
            continue
        dias = (fecha - f.fecha_vencimiento).days
        fila = {
            "factura_id": f.pk, "numero": f.numero_completo, "cliente_id": f.cliente_id,
            "cliente": f.cliente.razon_social, "tipo_cliente": f.cliente.tipo, "moneda": f.moneda,
            "fecha_emision": f.fecha_emision, "fecha_vencimiento": f.fecha_vencimiento,
            "dias_atraso": max(dias, 0), "rango": rango_de(dias), "estado": f.estado,
            "total": f.total, "saldo": saldo, "interes_mora": CERO, "tasa_mora": None,
            "total_con_interes": saldo, "aviso": None,
        }
        if dias > 0:
            try:
                r = calcular_interes_moratorio(f, fecha, registrar_alertas=False)
                if r["aplica"]:
                    fila.update(interes_mora=r["interes_acumulado"], tasa_mora=r["tasa_aplicada_anual"],
                                total_con_interes=r["total"])
            except ErrorTasaNoCargada as e:
                fila["aviso"] = str(e)
        filas.append(fila)
    return filas


def _totales_vacios():
    return {m: {"cantidad": 0, "saldo": CERO, "interes_mora": CERO, "total_con_interes": CERO} for m in MONEDAS}


def dashboard(fecha: date | None = None, moneda: str | None = None, dias_dso: int = 90) -> dict:
    fecha = fecha or timezone.localdate()
    filas = facturas_pendientes(fecha, moneda)
    grupos = OrderedDict((clave, {"rango": clave, "titulo": titulo, "facturas": [], "totales": _totales_vacios()})
                         for clave, titulo, _, _ in RANGOS)
    cartera = {m: {"cantidad": 0, "total_por_cobrar": CERO, "vencido": CERO, "corriente": CERO,
                   "interes_mora": CERO, "total_con_interes": CERO} for m in MONEDAS}
    for fila in filas:
        g, m = grupos[fila["rango"]], fila["moneda"]
        g["facturas"].append(fila)
        t = g["totales"][m]
        t["cantidad"] += 1
        t["saldo"] += fila["saldo"]
        t["interes_mora"] += fila["interes_mora"]
        t["total_con_interes"] += fila["total_con_interes"]
        c = cartera[m]
        c["cantidad"] += 1
        c["total_por_cobrar"] += fila["saldo"]
        c["vencido" if fila["dias_atraso"] > 0 else "corriente"] += fila["saldo"]
        c["interes_mora"] += fila["interes_mora"]
        c["total_con_interes"] += fila["total_con_interes"]
    monedas = [moneda] if moneda else list(MONEDAS)
    return {
        "fecha": fecha,
        "moneda": moneda,
        "cartera": {m: cartera[m] for m in monedas},
        "dso": {m: dso(m, fecha, dias_dso) for m in monedas},
        "aging": list(grupos.values()),
        "avisos": sorted({f["aviso"] for f in filas if f["aviso"]}),
    }


def dso(moneda: str, fecha: date, dias: int = 90) -> dict:
    """DSO = cuentas por cobrar ÷ ventas a crédito de los últimos `dias` días × `dias`.

    También se informa el plazo promedio REAL de cobro: días entre emisión y pago
    de los pagos recibidos en el período, ponderado por monto.
    """
    desde = fecha - timedelta(days=dias)
    base = Factura.objects.exclude(estado=Factura.Estado.ANULADA).filter(moneda=moneda)
    cxc = sum((f.calcular_saldo_pendiente(fecha) for f in base.filter(
        fecha_emision__lte=fecha, condicion=Factura.Condicion.CREDITO)), CERO)
    ventas = (base.filter(condicion=Factura.Condicion.CREDITO, fecha_emision__gt=desde, fecha_emision__lte=fecha)
              .aggregate(s=Sum("total"))["s"] or CERO)
    from apps.cobranzas.models import Pago

    pagos = Pago.objects.filter(moneda=moneda, anulado=False, fecha__gt=desde, fecha__lte=fecha,
                                factura__condicion=Factura.Condicion.CREDITO).select_related("factura")
    monto_pagos = sum((p.monto for p in pagos), CERO)
    ponderado = sum((p.monto * (p.fecha - p.factura.fecha_emision).days for p in pagos), CERO)
    return {
        "dias_periodo": dias,
        "cuentas_por_cobrar_credito": cxc,
        "ventas_credito_periodo": ventas,
        "dso": (cxc / ventas * dias).quantize(Decimal("0.1")) if ventas else None,
        "dias_promedio_cobro_real": (ponderado / monto_pagos).quantize(Decimal("0.1")) if monto_pagos else None,
        "pagos_considerados": len(pagos),
    }
