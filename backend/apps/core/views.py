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
    """Bitácora (sólo administradores).

    Filtros: ?modelo=facturacion.Factura &objeto_id= &usuario= &accion= &campo=fecha_vencimiento
    &desde=AAAA-MM-DD &hasta=AAAA-MM-DD
    """

    serializer_class = AuditLogSerializer
    permission_classes = [SoloAdministrador]

    def get_queryset(self):
        qs = AuditLog.objects.all()
        p = self.request.query_params
        for campo, filtro in (("modelo", "modelo"), ("objeto_id", "objeto_id"), ("accion", "accion"),
                              ("usuario", "usuario_nombre")):
            if p.get(campo):
                qs = qs.filter(**{filtro: p[campo]})
        if p.get("campo"):
            qs = qs.filter(cambios__has_key=p["campo"])
        if p.get("desde"):
            qs = qs.filter(fecha_hora__date__gte=p["desde"])
        if p.get("hasta"):
            qs = qs.filter(fecha_hora__date__lte=p["hasta"])
        return qs


class UsuarioListCreateView(generics.ListCreateAPIView):
    """Usuarios del CRM (sólo administradores). ?rol= &activo=true|false"""

    serializer_class = None
    permission_classes = [SoloAdministrador]

    def get_serializer_class(self):
        from .serializers import UsuarioAdminSerializer

        return UsuarioAdminSerializer

    def get_queryset(self):
        from .models import Usuario

        qs = Usuario.objects.order_by("username")
        p = self.request.query_params
        if p.get("rol"):
            qs = qs.filter(rol=p["rol"])
        if p.get("activo") in ("true", "false"):
            qs = qs.filter(is_active=p["activo"] == "true")
        return qs


class UsuarioDetailView(generics.RetrieveUpdateAPIView):
    """Cambiar rol, datos o activar/desactivar un usuario. Envíe "motivo" para la auditoría."""

    permission_classes = [SoloAdministrador]
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        from .serializers import UsuarioAdminSerializer

        return UsuarioAdminSerializer

    def get_queryset(self):
        from .models import Usuario

        return Usuario.objects.all()

    def perform_update(self, serializer):
        serializer.instance.motivo_auditoria = self.request.data.get("motivo", "")
        serializer.save()


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


# ------------------------- Sesión para el frontend ------------------------- #
from django.contrib.auth import authenticate, login, logout  # noqa: E402
from django.views.decorators.csrf import ensure_csrf_cookie  # noqa: E402
from rest_framework import status as http  # noqa: E402


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request):
    """Entrega la cookie csrftoken; el frontend la reenvía en el header X-CSRFToken."""
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def iniciar_sesion(request):
    u = authenticate(request, username=request.data.get("username", ""), password=request.data.get("password", ""))
    if u is None or not u.is_active:
        return Response({"detail": "Usuario o contraseña incorrectos."}, status=http.HTTP_400_BAD_REQUEST)
    login(request, u)
    return Response(UsuarioActualSerializer(u).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cerrar_sesion(request):
    logout(request)
    return Response({"ok": True})
