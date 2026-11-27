from django.contrib import admin

from .models import Feriado, GestionCobro, Pago, ParametrosCobranza


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    """Consulta de pagos. Se registran y anulan desde la pantalla o la API para mantener saldos y estados."""

    list_display = ("id", "factura", "fecha", "moneda", "monto", "medio", "referencia", "anulado")
    list_filter = ("medio", "moneda", "anulado")
    search_fields = ("factura__cliente__razon_social", "factura__numero", "referencia", "numero_recibo")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GestionCobro)
class GestionAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "cliente", "tipo", "resultado", "promesa_fecha", "promesa_monto",
                    "promesa_cumplida", "cobrador")
    list_filter = ("tipo", "resultado", "promesa_cumplida")
    search_fields = ("cliente__razon_social", "mensaje")


admin.site.register(ParametrosCobranza)
admin.site.register(Feriado)
