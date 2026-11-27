from datetime import date

from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.csv import respuesta_csv
from apps.core.views import montos_a_texto

from . import services


def fecha_param(request, nombre="fecha", default=None):
    valor = request.query_params.get(nombre)
    if not valor:
        return default
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise serializers.ValidationError({nombre: "Use el formato AAAA-MM-DD."})


def moneda_param(request):
    m = request.query_params.get("moneda") or None
    if m not in (None, "PYG", "USD"):
        raise serializers.ValidationError({"moneda": "Use PYG o USD."})
    return m


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """?moneda=PYG|USD &fecha=AAAA-MM-DD (corte) &dias_dso=90 &formato=csv"""
    datos = services.dashboard(fecha_param(request), moneda_param(request),
                               int(request.query_params.get("dias_dso", 90)))
    if request.query_params.get("formato") == "csv":
        filas = [f for g in datos["aging"] for f in g["facturas"]]
        return respuesta_csv(f"cartera_{datos['fecha']}", [
            ("rango", "Aging"), ("numero", "Factura"), ("cliente", "Cliente"), ("moneda", "Moneda"),
            ("fecha_emision", "Emisión"), ("fecha_vencimiento", "Vencimiento"), ("dias_atraso", "Días de atraso"),
            ("estado", "Estado"), ("total", "Total"), ("saldo", "Saldo"), ("tasa_mora", "Tasa mora % anual"),
            ("interes_mora", "Interés por mora"), ("total_con_interes", "Total con interés")], filas)
    return Response(montos_a_texto(datos))
