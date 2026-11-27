from datetime import date

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.clientes.models import Cliente
from apps.core.csv import respuesta_csv
from apps.core.views import montos_a_texto
from apps.tesoreria.views import fecha_param

from . import services


def _csv(request):
    return request.query_params.get("formato") == "csv"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def estado_cuenta(request, cliente_id):
    """?desde= &hasta= (por defecto, del 1 de enero a hoy) &formato=csv"""
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    hasta = fecha_param(request, "hasta", date.today())
    desde = fecha_param(request, "desde", date(hasta.year, 1, 1))
    if desde > hasta:
        raise serializers.ValidationError({"desde": "Debe ser anterior a 'hasta'."})
    datos = services.estado_cuenta(cliente, desde, hasta)
    if _csv(request):
        filas = [{**m, "moneda": mon} for mon, d in datos["monedas"].items() for m in
                 [{"fecha": desde, "tipo": "Saldo inicial", "saldo": d["saldo_inicial"]}] + d["movimientos"]]
        return respuesta_csv(f"estado_cuenta_{cliente.pk}_{desde}_{hasta}", [
            ("moneda", "Moneda"), ("fecha", "Fecha"), ("tipo", "Tipo"), ("documento", "Factura"),
            ("detalle", "Detalle"), ("debe", "Debe"), ("haber", "Haber"), ("saldo", "Saldo")], filas)
    return Response(montos_a_texto(datos))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def iva(request):
    """?anio= &mes= (por defecto, el mes actual) &formato=csv"""
    hoy = date.today()
    try:
        anio, mes = int(request.query_params.get("anio", hoy.year)), int(request.query_params.get("mes", hoy.month))
        date(anio, mes, 1)
    except ValueError:
        raise serializers.ValidationError({"mes": "Indique un año y un mes válidos."})
    datos = services.iva_periodo(anio, mes)
    if _csv(request):
        return respuesta_csv(f"iva_debito_{anio}_{mes:02d}", [
            ("fecha", "Fecha"), ("numero", "Factura"), ("timbrado", "Timbrado"), ("cdc", "CDC"),
            ("estado_sifen", "Estado SIFEN"), ("ruc", "RUC"), ("cliente", "Cliente"), ("moneda", "Moneda"),
            ("tipo_cambio", "Tipo de cambio"), ("base_imponible", "Base imponible"), ("iva", "IVA 10%"),
            ("total", "Total"), ("base_imponible_gs", "Base Gs."), ("iva_gs", "IVA Gs."), ("total_gs", "Total Gs."),
            ("retencion_iva_gs", "Retención IVA Gs.")], datos["facturas"])
    return Response(montos_a_texto(datos))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def oc_pendientes(request):
    """?cliente= &formato=csv"""
    datos = services.oc_pendientes(request.query_params.get("cliente"))
    if _csv(request):
        return respuesta_csv("oc_pendientes_conciliacion", [
            ("oc", "OC"), ("obra", "Obra"), ("factura", "Factura"), ("cliente", "Cliente"), ("moneda", "Moneda"),
            ("fecha_vencimiento", "Vencimiento"), ("dias_atraso", "Días de atraso"), ("total", "Total"),
            ("cobrado", "Cobrado"), ("saldo", "Saldo"), ("estado", "Estado")], datos["facturas_con_saldo"])
    return Response(montos_a_texto(datos))
