from django.contrib import admin
from django.urls import include, path

from apps.core.views import health

API_MODULOS = ["core", "clientes", "facturacion", "cobranzas", "intereses", "tesoreria", "reportes"]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api-auth/", include("rest_framework.urls")),
] + [path(f"api/{m}/", include(f"apps.{m}.urls")) for m in API_MODULOS]
