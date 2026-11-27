from django.urls import path

from .views import ClienteListCreateView

app_name = "clientes"
urlpatterns = [
    path("", ClienteListCreateView.as_view(), name="lista"),
]
