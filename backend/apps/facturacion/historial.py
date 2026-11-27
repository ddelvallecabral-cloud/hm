"""Historial de una factura: quién cambió su estado o vencimiento, pagos y gestiones de cobro.

La parte de auditoría (cambios de estado, vencimiento, importes, datos SIFEN y
anulaciones de pagos) sólo la ven tesorería y administración; las gestiones y
pagos los ven todos los roles.
"""
from apps.core.models import AuditLog

ETIQUETAS = {
    "estado": "Estado", "fecha_vencimiento": "Vencimiento", "plazo_dias": "Plazo (días)",
    "condicion": "Condición", "total": "Total", "saldo": "Saldo", "base_imponible": "Base imponible",
    "iva": "IVA", "orden_compra_id": "Orden de compra", "estado_sifen": "Estado SIFEN", "cdc": "CDC",
    "tasa_interes_anual": "Tasa pactada", "porcentaje_retencion_iva": "Retención IVA %",
    "motivo_anulacion": "Motivo de anulación", "anulado": "Anulado", "monto": "Monto", "fecha": "Fecha",
    "medio": "Medio", "referencia": "Referencia", "moneda": "Moneda", "factura_id": "Factura",
}
CAMPOS_CLAVE = ("estado", "fecha_vencimiento", "anulado", "saldo")


CAMPOS_MONTO = ("total", "saldo", "base_imponible", "iva", "monto")


def _legible(campo: str, valor, moneda: str):
    """Valor del registro de auditoría en formato para personas (montos, estados, fechas)."""
    from datetime import date
    from decimal import Decimal, InvalidOperation

    from .models import Factura

    if valor in (None, ""):
        return "—"
    if campo in CAMPOS_MONTO:
        try:
            d = Decimal(str(valor))
        except InvalidOperation:
            return valor
        if moneda == "USD":
            return "US$ " + f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return "Gs. " + f"{d:,.0f}".replace(",", ".")
    if campo == "estado":
        return dict(Factura.Estado.choices).get(valor, valor)
    if campo == "estado_sifen":
        return dict(Factura.EstadoSifen.choices).get(valor, valor)
    if campo in ("fecha_vencimiento", "fecha"):
        try:
            return date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
        except ValueError:
            return valor
    if isinstance(valor, bool) or valor in ("True", "False"):
        return "Sí" if valor in (True, "True") else "No"
    return valor


def _cambios_legibles(cambios: dict, moneda: str, solo_clave=False) -> list[dict]:
    out = []
    for campo, (antes, despues) in cambios.items():
        if solo_clave and campo not in CAMPOS_CLAVE:
            continue
        out.append({"campo": campo, "etiqueta": ETIQUETAS.get(campo, campo), "antes": _legible(campo, antes, moneda),
                    "despues": _legible(campo, despues, moneda), "antes_valor": antes, "despues_valor": despues})
    return out


def historial_factura(factura, ver_auditoria: bool) -> dict:
    pagos = list(factura.pagos.select_related("registrado_por").order_by("-fecha", "-id"))
    gestiones = list(factura.gestiones.select_related("cobrador", "revisada_por").order_by("-fecha_hora", "-id"))
    eventos = []
    for p in pagos:
        eventos.append({
            "fecha_hora": p.creado_en, "tipo": "pago",
            "usuario": p.registrado_por.username if p.registrado_por else None,
            "titulo": f"Pago {'anulado' if p.anulado else 'registrado'}: {_legible('monto', p.monto, p.moneda)}",
            "detalle": f"{p.get_medio_display()}{' · ' + p.referencia if p.referencia else ''} · fecha valor "
                       f"{p.fecha:%d/%m/%Y}{' · motivo: ' + p.motivo_anulacion if p.anulado else ''}",
        })
    for g in gestiones:
        eventos.append({
            "fecha_hora": g.fecha_hora, "tipo": "gestion",
            "usuario": g.cobrador.username if g.cobrador else None,
            "titulo": f"{g.get_tipo_display()}{' · ' + g.get_resultado_display() if g.resultado else ''}",
            "detalle": g.mensaje_final or g.mensaje,
        })
    auditoria = []
    if ver_auditoria:
        logs = list(AuditLog.objects.filter(modelo="facturacion.Factura", objeto_id=str(factura.pk)))
        pagos_ids = [str(p.pk) for p in pagos]
        logs += list(AuditLog.objects.filter(modelo="cobranzas.Pago", objeto_id__in=pagos_ids, accion="modificar"))
        for log in sorted(logs, key=lambda x: x.fecha_hora, reverse=True):
            fila = {"fecha_hora": log.fecha_hora, "usuario": log.usuario_nombre or "sistema", "accion": log.accion,
                    "modelo": "Pago" if log.modelo == "cobranzas.Pago" else "Factura", "objeto_id": log.objeto_id,
                    "motivo": log.motivo, "cambios": _cambios_legibles(log.cambios, factura.moneda, solo_clave=log.accion == "crear")}
            auditoria.append(fila)
            if log.accion == "modificar" and any(c["campo"] in CAMPOS_CLAVE for c in fila["cambios"]):
                eventos.append({
                    "fecha_hora": log.fecha_hora, "tipo": "auditoria", "usuario": fila["usuario"],
                    "titulo": "Cambio: " + ", ".join(f"{c['etiqueta']} {c['antes']} → {c['despues']}"
                                                    for c in fila["cambios"] if c["campo"] in CAMPOS_CLAVE),
                    "detalle": log.motivo,
                })
    eventos.sort(key=lambda e: e["fecha_hora"], reverse=True)
    return {"factura_id": factura.pk, "numero": factura.numero_completo, "ver_auditoria": ver_auditoria,
            "linea_de_tiempo": eventos, "auditoria": auditoria}
