from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.clientes.models import Cliente
from apps.core.permissions import LecturaTodosEscrituraTesorero
from apps.core.views import montos_a_texto

from . import services
from .models import GestionCobro, Pago
from .serializers import (
    CobroContadoSerializer, GestionActualizacionSerializer, GestionCobroSerializer, ImputacionSerializer,
    PagoSerializer, a_drf,
)


def _filtrar(qs, params, campos):
    for campo in campos:
        if params.get(campo):
            qs = qs.filter(**{campo: params[campo]})
    return qs


# ------------------------------- Pagos ---------------------------------- #
class PagoListCreateView(generics.ListCreateAPIView):
    """GET ?cliente= &moneda= &medio= &anulado=  ·  POST: registra un pago (tesorero)."""

    serializer_class = PagoSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]

    def get_queryset(self):
        qs = Pago.objects.select_related("cliente").prefetch_related("aplicaciones__factura")
        return _filtrar(qs, self.request.query_params, ("cliente", "moneda", "medio", "anulado"))


class PagoDetailView(generics.RetrieveAPIView):
    queryset = Pago.objects.select_related("cliente").prefetch_related("aplicaciones__factura")
    serializer_class = PagoSerializer


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def aplicar_pago(request, pk):
    """Aplica el saldo a favor de un pago: {"imputaciones": [{"factura": 1, "monto": "500000"}]}."""
    pago = get_object_or_404(Pago, pk=pk)
    ser = ImputacionSerializer(data=request.data.get("imputaciones", []), many=True)
    ser.is_valid(raise_exception=True)
    try:
        services.aplicar_pago(pago, ser.validated_data)
    except DjangoValidationError as e:
        raise a_drf(e)
    pago.refresh_from_db()
    return Response(PagoSerializer(pago).data)


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def anular_pago(request, pk):
    pago = get_object_or_404(Pago, pk=pk)
    try:
        pago = services.anular_pago(pago, (request.data.get("motivo") or "").strip())
    except DjangoValidationError as e:
        raise a_drf(e)
    return Response(PagoSerializer(pago).data)


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def cobro_contado(request):
    """{"factura": 12, "medio": "efectivo"} → cobra el saldo y deja la factura pagada."""
    ser = CobroContadoSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    try:
        pago = services.registrar_cobro_contado(usuario=request.user, **ser.validated_data)
    except DjangoValidationError as e:
        raise a_drf(e)
    return Response(PagoSerializer(pago).data, status=status.HTTP_201_CREATED)


# ------------------------------ Gestiones ------------------------------- #
class GestionListCreateView(generics.ListCreateAPIView):
    """Todos los roles registran gestiones. GET ?cliente= &tipo= &resultado= &factura="""

    serializer_class = GestionCobroSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        p = self.request.query_params
        qs = _filtrar(GestionCobro.objects.select_related("cliente", "cobrador").prefetch_related("facturas"),
                      p, ("cliente", "tipo", "resultado"))
        if p.get("factura"):
            qs = qs.filter(facturas=p["factura"])
        if p.get("promesas_pendientes"):
            qs = qs.filter(resultado=GestionCobro.Resultado.PROMESA_PAGO, promesa_cumplida__isnull=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(cobrador=self.request.user)


class GestionDetailView(generics.RetrieveUpdateAPIView):
    queryset = GestionCobro.objects.select_related("cliente", "cobrador")
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        return GestionCobroSerializer if self.request.method == "GET" else GestionActualizacionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        # Un cobrador sólo modifica sus propias gestiones.
        if self.request.method != "GET" and not u.es_tesorero:
            qs = qs.filter(Q(cobrador=u))
        return qs


# --------------------------- Consultas ---------------------------------- #
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def alertas(request):
    """Vencimientos próximos (?dias=5) y facturas vencidas."""
    dias = request.query_params.get("dias")
    return Response(montos_a_texto(services.alertas_vencimiento(dias=int(dias) if dias else None)))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cuenta_corriente(request, cliente_id):
    return Response(montos_a_texto(services.cuenta_corriente(get_object_or_404(Cliente, pk=cliente_id))))
