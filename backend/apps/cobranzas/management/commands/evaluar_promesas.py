"""Marca promesas de pago vencidas como cumplidas / incumplidas. Programar a diario."""
from django.core.management.base import BaseCommand

from apps.cobranzas.services import evaluar_promesas


class Command(BaseCommand):
    help = "Evalúa las promesas de pago cuya fecha ya pasó."

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(f"{evaluar_promesas()} promesa(s) evaluadas."))
