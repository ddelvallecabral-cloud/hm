from django.contrib import admin

from .models import Factura, ItemFactura, OrdenCompra


class ItemInline(admin.TabularInline):
    model = ItemFactura
    readonly_fields = ("base_imponible", "iva", "total")
    extra = 0


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    inlines = [ItemInline]
    list_display = ("numero_completo", "cliente", "fecha_emision", "fecha_vencimiento", "moneda",
                    "total", "iva_10", "saldo", "estado", "estado_sifen")
    list_filter = ("estado", "estado_sifen", "moneda", "condicion")
    search_fields = ("numero", "cdc", "cliente__razon_social", "cliente__ruc")
    readonly_fields = ("gravada_10", "iva_10", "gravada_5", "iva_5", "exenta", "total", "retencion_iva", "saldo")


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "fecha", "moneda", "monto_total", "estado")
    list_filter = ("estado", "moneda")
    search_fields = ("numero", "cliente__razon_social")
