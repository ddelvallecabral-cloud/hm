from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core.permissions import LecturaTodosEscrituraTesorero

from .models import Factura, OrdenCompra
from .serializers import FacturaActualizacionSerializer, FacturaSerializer, OrdenCompraSerializer, _a_drf
from .services.emision import anular_factura


class OrdenCompraListCreateView(generics.ListCreateAPIView):
    """?cliente=<id> &estado="""

    serializer_class = OrdenCompraSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]

    def get_queryset(self):
        qs = OrdenCompra.objects.select_related("cliente")
        for campo in ("cliente", "estado"):
            if self.request.query_params.get(campo):
                qs = qs.filter(**{campo: self.request.query_params[campo]})
        return qs


class FacturaListCreateView(generics.ListCreateAPIView):
    """?cliente= &estado= &moneda= &condicion= &estado_sifen="""

    serializer_class = FacturaSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]

    def get_queryset(self):
        qs = Factura.objects.select_related("cliente", "orden_compra").prefetch_related("items")
        for campo in ("cliente", "estado", "moneda", "condicion", "estado_sifen"):
            if self.request.query_params.get(campo):
                qs = qs.filter(**{campo: self.request.query_params[campo]})
        return qs


class FacturaDetailView(generics.RetrieveUpdateAPIView):
    queryset = Factura.objects.select_related("cliente", "orden_compra").prefetch_related("items")
    permission_classes = [LecturaTodosEscrituraTesorero]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return FacturaSerializer if self.request.method == "GET" else FacturaActualizacionSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(FacturaSerializer(self.get_object()).data)


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def anular(request, pk):
    factura = get_object_or_404(Factura, pk=pk)
    try:
        factura = anular_factura(factura, (request.data.get("motivo") or "").strip())
    except DjangoValidationError as e:
        raise _a_drf(e)
    return Response(FacturaSerializer(factura).data)
