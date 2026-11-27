from django.db import connection
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import AuditLog
from .permissions import SoloAdministrador
from .serializers import AuditLogSerializer, UsuarioActualSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Chequeo de vida para Docker/balanceadores: verifica la conexión a la base."""
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        db = "ok"
    except Exception:  # noqa: BLE001
        db = "error"
    return Response({"status": "ok" if db == "ok" else "degraded", "database": db},
                    status=200 if db == "ok" else 503)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Usuario logueado y su rol (el frontend lo usa para mostrar/ocultar acciones)."""
    return Response(UsuarioActualSerializer(request.user).data)


class AuditLogListView(generics.ListAPIView):
    """Bitácora (sólo administradores). Filtros: ?modelo=facturacion.Factura &objeto_id= &usuario= &accion="""

    serializer_class = AuditLogSerializer
    permission_classes = [SoloAdministrador]

    def get_queryset(self):
        qs = AuditLog.objects.all()
        p = self.request.query_params
        for campo, filtro in (("modelo", "modelo"), ("objeto_id", "objeto_id"), ("accion", "accion"),
                              ("usuario", "usuario_nombre")):
            if p.get(campo):
                qs = qs.filter(**{filtro: p[campo]})
        return qs


def montos_a_texto(obj):
    """Convierte Decimal a str en estructuras anidadas (los montos nunca se envían como float)."""
    from decimal import Decimal

    if isinstance(obj, Decimal):
        return f"{obj:.2f}"
    if isinstance(obj, dict):
        return {k: montos_a_texto(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [montos_a_texto(v) for v in obj]
    return obj
