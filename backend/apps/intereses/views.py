from datetime import date

from rest_framework import generics, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import LecturaTodosEscrituraTesorero
from apps.core.views import montos_a_texto
from apps.facturacion.models import Factura

from .models import AlertaTasa, TasaReferenciaBCP
from .serializers import AlertaTasaSerializer, TasaReferenciaBCPSerializer
from .services import ErrorTasaNoCargada, calcular_interes_moratorio


class LecturaTodosEscrituraAdmin(BasePermission):
    message = "Sólo un administrador carga o modifica tasas del BCP."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (request.method in SAFE_METHODS or u.es_administrador))


class TasaListCreateView(generics.ListCreateAPIView):
    """Tasas máximas BCP. ?moneda= &anio="""

    serializer_class = TasaReferenciaBCPSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]

    def get_queryset(self):
        qs = TasaReferenciaBCP.objects.all()
        for campo in ("moneda", "anio"):
            if self.request.query_params.get(campo):
                qs = qs.filter(**{campo: self.request.query_params[campo]})
        return qs


class TasaDetailView(generics.RetrieveUpdateAPIView):
    queryset = TasaReferenciaBCP.objects.all()
    serializer_class = TasaReferenciaBCPSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    http_method_names = ["get", "patch", "head", "options"]


class AlertaListView(generics.ListAPIView):
    """Alertas de ajuste de tasa. ?revisada=false"""

    serializer_class = AlertaTasaSerializer

    def get_queryset(self):
        qs = AlertaTasa.objects.select_related("factura__cliente")
        r = self.request.query_params.get("revisada")
        if r in ("true", "false"):
            qs = qs.filter(revisada=(r == "true"))
        return qs


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def marcar_alerta_revisada(request, pk):
    alerta = get_object_or_404(AlertaTasa, pk=pk)
    alerta.revisada = True
    alerta.save(update_fields=["revisada"])
    return Response(AlertaTasaSerializer(alerta).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def interes_factura(request, pk):
    """Interés moratorio de una factura a hoy o a ?fecha=AAAA-MM-DD.

    Con una fecha futura funciona como simulador (supone que no habrá más pagos hasta esa fecha).
    """
    factura = get_object_or_404(Factura.objects.select_related("cliente"), pk=pk)
    try:
        fecha = date.fromisoformat(request.query_params["fecha"]) if request.query_params.get("fecha") else None
    except ValueError:
        raise serializers.ValidationError({"fecha": "Use el formato AAAA-MM-DD."})
    try:
        resultado = calcular_interes_moratorio(factura, fecha)
    except ErrorTasaNoCargada as e:
        return Response({"detail": str(e)}, status=409)
    return Response(montos_a_texto(resultado))
