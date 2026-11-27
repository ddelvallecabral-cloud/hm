"""Permisos por rol para la API (ver tabla en core.models.Usuario)."""
from rest_framework.permissions import SAFE_METHODS, BasePermission


def _autenticado(request):
    return bool(request.user and request.user.is_authenticated)


class LecturaTodosEscrituraTesorero(BasePermission):
    """Cualquier rol consulta; sólo tesorero o administrador crean/modifican."""

    message = "Sólo tesorería o administración pueden realizar esta acción."

    def has_permission(self, request, view):
        if not _autenticado(request):
            return False
        return request.method in SAFE_METHODS or request.user.es_tesorero


class SoloAdministrador(BasePermission):
    message = "Sólo un administrador puede realizar esta acción."

    def has_permission(self, request, view):
        return _autenticado(request) and request.user.es_administrador
