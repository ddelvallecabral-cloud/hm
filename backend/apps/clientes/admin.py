from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "ruc", "tipo", "condicion_pago", "plazo_dias", "limite_credito",
                    "requiere_orden_compra", "activo")
    list_filter = ("tipo", "condicion_pago", "requiere_orden_compra", "activo")
    search_fields = ("razon_social", "ruc")
    readonly_fields = ("requiere_orden_compra",)
