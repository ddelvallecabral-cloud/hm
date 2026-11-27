"""Recomendaciones de comunicación según el atraso de la factura.

Son SUGERENCIAS para el cobrador y tesorería: tono, canal y un texto modelo
con los datos reales de la factura. Tesorería decide qué comunicar finalmente.
Revisar los textos con la asesoría legal y adaptarlos al estilo de la empresa.
"""
from django.utils import timezone

BUENAS_PRACTICAS = [
    "Identifíquese con nombre y empresa, y hable sólo con el titular o el contacto autorizado.",
    "Informe datos concretos: número de factura, monto pendiente y fecha de vencimiento.",
    "Ofrezca opciones: transferencia, cheque, pago parcial o un plan de pagos.",
    "No mencione consecuencias legales que no se vayan a iniciar ni involucre a terceros.",
    "Registre la promesa de pago con fecha y monto, y confírmela por escrito.",
    "Si el cliente cuestiona la factura, registre el reclamo y suspenda el reclamo de pago hasta aclararlo.",
]

TRAMOS = [
    # (desde días de atraso, hasta, clave, tono, canal, plantilla)
    (None, 0, "por_vencer", "Recordatorio cordial", "Correo o WhatsApp (si hay consentimiento)",
     "Estimado/a {cliente}: le recordamos que la factura {factura} por {moneda} {saldo} vence el {vencimiento}. "
     "Si ya realizó el pago, por favor desestime este mensaje. Quedamos a disposición. Tesorería."),
    (1, 15, "atraso_leve", "Cordial e informativo", "Llamada o correo",
     "Estimado/a {cliente}: según nuestros registros, la factura {factura} por {moneda} {saldo} venció el "
     "{vencimiento} y figura pendiente. ¿Podría indicarnos la fecha estimada de pago? Si ya pagó, le pedimos "
     "el comprobante para conciliarlo. Muchas gracias. Tesorería."),
    (16, 30, "atraso_moderado", "Formal y colaborativo", "Llamada y correo de confirmación",
     "Estimado/a {cliente}: la factura {factura} registra {dias} días de atraso, con un saldo de {moneda} {saldo}. "
     "Queremos ayudarle a regularizarla: podemos coordinar un pago parcial o un plan de pagos. "
     "Por favor indíquenos qué opción le resulta conveniente. Tesorería."),
    (31, 60, "atraso_alto", "Formal, propuesta concreta", "Llamada del tesorero y nota formal",
     "Estimado/a {cliente}: la factura {factura} lleva {dias} días vencida (saldo {moneda} {saldo}). "
     "Le proponemos acordar un plan de pagos esta semana. Mientras el saldo esté pendiente, las nuevas compras "
     "a crédito quedan sujetas a revisión. Quedamos atentos a su respuesta. Tesorería."),
    (61, None, "atraso_critico", "Formal; evaluar con asesoría legal", "Nota formal / reunión",
     "Estimado/a {cliente}: la factura {factura} registra {dias} días de atraso (saldo {moneda} {saldo}). "
     "Le solicitamos una reunión para acordar la regularización. De no llegar a un acuerdo, la empresa evaluará "
     "con su asesoría las acciones que correspondan. Tesorería."),
]


def _fmt(monto, moneda):
    if moneda == "PYG":
        return f"{monto:,.0f}".replace(",", ".")
    return f"{monto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def recomendacion_para(factura, hoy=None) -> dict:
    hoy = hoy or timezone.localdate()
    dias = (hoy - factura.fecha_vencimiento).days
    for desde, hasta, clave, tono, canal, plantilla in TRAMOS:
        if (desde is None or dias >= desde) and (hasta is None or dias <= hasta):
            break
    texto = plantilla.format(
        cliente=factura.cliente.razon_social, factura=factura.numero_completo, moneda=factura.moneda,
        saldo=_fmt(factura.saldo, factura.moneda), vencimiento=factura.fecha_vencimiento.strftime("%d/%m/%Y"),
        dias=max(dias, 0),
    )
    return {"factura_id": factura.pk, "numero": factura.numero_completo, "dias_atraso": max(dias, 0),
            "tramo": clave, "tono": tono, "canal_sugerido": canal, "mensaje_sugerido": texto,
            "buenas_practicas": BUENAS_PRACTICAS}
