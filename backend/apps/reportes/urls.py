from django.urls import path

from . import views

app_name = "reportes"
urlpatterns = [
    path("estado-cuenta/<int:cliente_id>/", views.estado_cuenta, name="estado-cuenta"),
    path("iva/", views.iva, name="iva"),
    path("oc-pendientes/", views.oc_pendientes, name="oc-pendientes"),
]
