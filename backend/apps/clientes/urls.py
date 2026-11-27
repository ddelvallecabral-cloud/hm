from django.urls import path

from .views import ClienteDetailView, ClienteListCreateView

app_name = "clientes"
urlpatterns = [
    path("", ClienteListCreateView.as_view(), name="lista"),
    path("<int:pk>/", ClienteDetailView.as_view(), name="detalle"),
]
