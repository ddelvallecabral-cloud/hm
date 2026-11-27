from django.urls import path

from .views import AuditLogListView, cerrar_sesion, csrf, iniciar_sesion, me

app_name = "core"
urlpatterns = [
    path("me/", me, name="me"),
    path("csrf/", csrf, name="csrf"),
    path("login/", iniciar_sesion, name="login"),
    path("logout/", cerrar_sesion, name="logout"),
    path("auditoria/", AuditLogListView.as_view(), name="auditoria"),
]
