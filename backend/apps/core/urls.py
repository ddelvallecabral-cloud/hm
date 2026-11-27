from django.urls import path

from .views import (
    AuditLogListView, UsuarioDetailView, UsuarioListCreateView, cerrar_sesion, csrf, iniciar_sesion, me,
)

app_name = "core"
urlpatterns = [
    path("me/", me, name="me"),
    path("csrf/", csrf, name="csrf"),
    path("login/", iniciar_sesion, name="login"),
    path("logout/", cerrar_sesion, name="logout"),
    path("auditoria/", AuditLogListView.as_view(), name="auditoria"),
    path("usuarios/", UsuarioListCreateView.as_view(), name="usuarios"),
    path("usuarios/<int:pk>/", UsuarioDetailView.as_view(), name="usuario"),
]
