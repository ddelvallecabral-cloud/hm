"""Carga las tasas BCP de referencia de enero y agosto de 2026 indicadas en la especificación.

    python manage.py cargar_tasas_ejemplo

IMPORTANTE: son valores de referencia provistos en el pedido del proyecto. Antes
de usarlos para cobrar, verifíquelos contra la publicación oficial del BCP y
cargue cada mes el valor vigente.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.intereses.models import TasaReferenciaBCP

FUENTE = "Valor de referencia de la especificación del proyecto. VERIFICAR con la publicación oficial del BCP."
TASAS = [(2026, 1, "PYG", "27.06"), (2026, 1, "USD", "11.04"), (2026, 8, "PYG", "27.26"), (2026, 8, "USD", "11.25")]


class Command(BaseCommand):
    help = "Carga tasas BCP de ejemplo (enero y agosto 2026)."

    def handle(self, *args, **opts):
        for anio, mes, moneda, tasa in TASAS:
            _, creada = TasaReferenciaBCP.objects.get_or_create(
                anio=anio, mes=mes, moneda=moneda, defaults={"tasa_maxima_anual": Decimal(tasa), "fuente": FUENTE})
            self.stdout.write(f"{mes:02d}/{anio} {moneda} {tasa}% {'cargada' if creada else 'ya existía'}")
