from django.contrib import admin

from .models import AlertaTasa, TasaReferenciaBCP


@admin.register(TasaReferenciaBCP)
class TasaAdmin(admin.ModelAdmin):
    list_display = ("anio", "mes", "moneda", "tasa_maxima_anual", "fuente")
    list_filter = ("moneda", "anio")


@admin.register(AlertaTasa)
class AlertaTasaAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "factura", "tipo", "tasa_pactada_anual", "tope_aplicado_anual", "periodo_tope",
                    "revisada")
    list_filter = ("tipo", "moneda", "revisada")
    readonly_fields = ("factura", "tipo", "moneda", "tasa_pactada_anual", "tope_aplicado_anual", "periodo_tope",
                       "mensaje", "creado_en")
