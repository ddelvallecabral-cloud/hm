from django.db.models import Q
from rest_framework import generics

from apps.core.permissions import LecturaTodosEscrituraTesorero

from .models import Cliente
from .serializers import ClienteSerializer


class ClienteListCreateView(generics.ListCreateAPIView):
    """GET: lista clientes (filtros ?tipo=, ?condicion_pago=, ?q= razón social o RUC).
    POST: crea un cliente (tesorero/administrador).
    """

    serializer_class = ClienteSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]

    def get_queryset(self):
        qs = Cliente.objects.all()
        p = self.request.query_params
        if p.get("tipo"):
            qs = qs.filter(tipo=p["tipo"])
        if p.get("condicion_pago"):
            qs = qs.filter(condicion_pago=p["condicion_pago"])
        if p.get("q"):
            qs = qs.filter(Q(razon_social__icontains=p["q"]) | Q(ruc__startswith=p["q"]))
        return qs


class ClienteDetailView(generics.RetrieveUpdateAPIView):
    """GET / PATCH de un cliente. Envíe "motivo" para dejarlo en la auditoría."""

    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [LecturaTodosEscrituraTesorero]
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        serializer.instance.motivo_auditoria = self.request.data.get("motivo", "")
        serializer.save()
