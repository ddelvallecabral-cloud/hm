from django.contrib import admin

from .models import AplicacionPago, Feriado, GestionCobro, Pago, ParametrosCobranza


class AplicacionInline(admin.TabularInline):
    model = AplicacionPago
    extra = 0
    readonly_fields = ("factura", "monto", "creado_en")

    def has_add_permission(self, request, obj=None):
        return False  # se aplican desde la API para mantener saldos consistentes


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    inlines = [AplicacionInline]
    list_display = ("id", "cliente", "fecha", "moneda", "monto", "medio", "referencia", "anulado")
    list_filter = ("medio", "moneda", "anulado")
    search_fields = ("cliente__razon_social", "referencia", "numero_recibo")
    readonly_fields = ("anulado", "motivo_anulacion", "registrado_por")


@admin.register(GestionCobro)
class GestionAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "cliente", "tipo", "resultado", "promesa_fecha", "promesa_monto",
                    "promesa_cumplida", "cobrador")
    list_filter = ("tipo", "resultado", "promesa_cumplida")
    search_fields = ("cliente__razon_social", "mensaje")


admin.site.register(ParametrosCobranza)
admin.site.register(Feriado)
