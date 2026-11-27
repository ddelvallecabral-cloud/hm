from django.urls import path

from . import views

app_name = "intereses"
urlpatterns = [
    path("tasas-bcp/", views.TasaListCreateView.as_view(), name="tasas"),
    path("tasas-bcp/<int:pk>/", views.TasaDetailView.as_view(), name="tasa"),
    path("alertas/", views.AlertaListView.as_view(), name="alertas"),
    path("alertas/<int:pk>/revisada/", views.marcar_alerta_revisada, name="alerta-revisada"),
    path("facturas/<int:pk>/", views.interes_factura, name="interes-factura"),
]
