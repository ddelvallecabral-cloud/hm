from django.urls import path

from . import views

app_name = "facturacion"
urlpatterns = [
    path("facturas/", views.FacturaListCreateView.as_view(), name="facturas"),
    path("facturas/<int:pk>/", views.FacturaDetailView.as_view(), name="factura"),
    path("facturas/<int:pk>/anular/", views.anular, name="anular"),
    path("ordenes-compra/", views.OrdenCompraListCreateView.as_view(), name="ordenes-compra"),
]
