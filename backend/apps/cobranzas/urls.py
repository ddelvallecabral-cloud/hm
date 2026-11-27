from django.urls import path

from . import views

app_name = "cobranzas"
urlpatterns = [
    path("cobro-contado/", views.cobro_contado, name="cobro-contado"),
    path("registrar-cobranza/", views.registrar_cobranza, name="registrar-cobranza"),
    path("facturas-por-cobrar/", views.facturas_por_cobrar, name="facturas-por-cobrar"),
    path("pagos/", views.PagoListCreateView.as_view(), name="pagos"),
    path("pagos/<int:pk>/", views.PagoDetailView.as_view(), name="pago"),
    path("pagos/<int:pk>/anular/", views.anular_pago, name="anular"),
    path("gestiones/", views.GestionListCreateView.as_view(), name="gestiones"),
    path("gestiones/<int:pk>/", views.GestionDetailView.as_view(), name="gestion"),
    path("gestiones/<int:pk>/revisar/", views.revisar_gestion, name="revisar"),
    path("gestiones/verificar/", views.verificar_gestion, name="verificar"),
    path("recomendaciones/", views.recomendaciones, name="recomendaciones"),
    path("alertas/", views.alertas, name="alertas"),
    path("cuenta-corriente/<int:cliente_id>/", views.cuenta_corriente, name="cuenta-corriente"),
]
