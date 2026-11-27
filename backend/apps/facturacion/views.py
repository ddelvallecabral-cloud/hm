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
    """?q=<número, cliente o RUC> &cliente= &estado= &moneda= &condicion= &estado_sifen="""

    serializer_class = FacturaSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]

    def get_queryset(self):
        qs = Factura.objects.select_related("cliente", "orden_compra").prefetch_related("items")
        for campo in ("cliente", "estado", "moneda", "condicion", "estado_sifen"):
            if self.request.query_params.get(campo):
                qs = qs.filter(**{campo: self.request.query_params[campo]})
        if self.request.query_params.get("q"):
            qs = qs.filter(filtro_busqueda(self.request.query_params["q"]))
        return qs


def filtro_busqueda(q: str):
    """Busca por número (001-001-0000123, 0000123 o 123), razón social o RUC."""
    from django.db.models import Q

    q = q.strip()
    filtro = Q(cliente__razon_social__icontains=q) | Q(cliente__ruc__startswith=q)
    partes = q.replace(" ", "").split("-")
    if all(p.isdigit() for p in partes):
        if len(partes) == 3:
            filtro |= Q(establecimiento=partes[0].zfill(3), punto_expedicion=partes[1].zfill(3),
                        numero=partes[2].zfill(7))
        elif len(partes) == 1 and len(partes[0]) <= 7:
            filtro |= Q(numero=partes[0].zfill(7))
    return filtro


@api_view(["GET"])
def historial(request, pk):
    """Línea de tiempo de la factura: pagos, gestiones de cobro y (tesorería) quién cambió estado o vencimiento."""
    from apps.core.views import montos_a_texto

    from .historial import historial_factura

    factura = get_object_or_404(Factura, pk=pk)
    return Response(montos_a_texto(historial_factura(factura, ver_auditoria=request.user.es_tesorero)))


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
