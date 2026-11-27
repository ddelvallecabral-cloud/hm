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
from apps.facturacion.models import Factura

from .recomendaciones import BUENAS_PRACTICAS, recomendacion_para
from .serializers import (
    CobroContadoSerializer, GestionActualizacionSerializer, GestionCobroSerializer, PagoSerializer,
    RevisionGestionSerializer, a_drf,
)


def _filtrar(qs, params, campos):
    for campo in campos:
        if params.get(campo):
            qs = qs.filter(**{campo: params[campo]})
    return qs


# ------------------------------- Pagos ---------------------------------- #
class PagoListCreateView(generics.ListCreateAPIView):
    """GET ?factura= &cliente= &moneda= &medio= &anulado=  ·  POST: pago de una factura (tesorero)."""

    serializer_class = PagoSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]

    def get_queryset(self):
        p = self.request.query_params
        qs = _filtrar(Pago.objects.select_related("factura__cliente"), p, ("factura", "moneda", "medio", "anulado"))
        if p.get("cliente"):
            qs = qs.filter(factura__cliente_id=p["cliente"])
        return qs


class PagoDetailView(generics.RetrieveAPIView):
    queryset = Pago.objects.select_related("factura__cliente")
    serializer_class = PagoSerializer


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


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def registrar_cobranza(request):
    """Igual que POST /pagos/, pero devuelve además el resumen actualizado de la factura (lo usa la pantalla)."""
    ser = PagoSerializer(data=request.data, context={"request": request})
    ser.is_valid(raise_exception=True)
    pago = ser.save()
    pago.factura.refresh_from_db()
    return Response({"pago": PagoSerializer(pago).data, "factura": _factura_resumen(pago.factura)},
                    status=status.HTTP_201_CREATED)


def _factura_resumen(f: Factura) -> dict:
    return montos_a_texto({
        "id": f.pk, "numero": f.numero_completo, "cliente_id": f.cliente_id, "cliente": f.cliente.razon_social,
        "ruc": f.cliente.ruc, "fecha_emision": f.fecha_emision, "fecha_vencimiento": f.fecha_vencimiento,
        "condicion": f.condicion, "moneda": f.moneda, "total": f.total, "saldo": f.calcular_saldo_pendiente(),
        "cobrado": f.total - f.calcular_saldo_pendiente(), "estado": f.estado, "estado_display": f.get_estado_display(),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def facturas_por_cobrar(request):
    """Buscador para "Registrar cobranza": ?q=<cliente, RUC o número> &cliente= &moneda="""
    p = request.query_params
    facturas = services.buscar_facturas_por_cobrar(p.get("q", ""), p.get("cliente"), p.get("moneda"))
    return Response([_factura_resumen(f) for f in facturas])


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
        if p.get("revision"):
            qs = qs.filter(revision=p["revision"])
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


@api_view(["POST"])
@permission_classes([LecturaTodosEscrituraTesorero])
def revisar_gestion(request, pk):
    """Tesorería decide: {"decision": "aprobada"} o {"decision": "modificada", "mensaje_final": "…"}."""
    g = get_object_or_404(GestionCobro, pk=pk)
    ser = RevisionGestionSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    d = ser.validated_data
    try:
        g = services.revisar_gestion(g, request.user, d["decision"], d["mensaje_final"], d["comentario"])
    except DjangoValidationError as e:
        raise a_drf(e)
    return Response(GestionCobroSerializer(g).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verificar_gestion(request):
    """Muestra las alertas que tendría una gestión, sin guardarla (para revisar el mensaje antes de enviarlo)."""
    ser = GestionCobroSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    datos = {k: v for k, v in ser.validated_data.items() if k != "facturas"}
    return Response({"alertas": GestionCobro(**datos).evaluar_alertas()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recomendaciones(request):
    """?factura=<id> → tono, canal y mensaje sugerido según los días de atraso."""
    if request.query_params.get("factura"):
        f = get_object_or_404(Factura.objects.select_related("cliente"), pk=request.query_params["factura"])
        return Response(recomendacion_para(f))
    return Response({"buenas_practicas": BUENAS_PRACTICAS})


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
