"""Marca como "vencidas" las facturas con saldo cuyo vencimiento ya pasó.

Programar una vez por día (p. ej. cron 00:05, hora de Asunción):
    python manage.py actualizar_vencidas
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.facturacion.models import Factura


class Command(BaseCommand):
    help = "Actualiza el estado de las facturas vencidas."

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="Fecha de referencia AAAA-MM-DD (por defecto, hoy).")

    def handle(self, *args, **opts):
        from datetime import date

        hoy = date.fromisoformat(opts["fecha"]) if opts.get("fecha") else timezone.localdate()
        n = 0
        for f in Factura.objects.filter(estado__in=[Factura.Estado.PENDIENTE, Factura.Estado.PAGADA_PARCIAL],
                                        fecha_vencimiento__lt=hoy):
            f.actualizar_estado(hoy)
            f.motivo_auditoria = "Vencimiento automático"
            f.save(update_fields=["estado", "actualizado_en"])
            n += 1
        self.stdout.write(self.style.SUCCESS(f"{n} factura(s) marcadas como vencidas al {hoy}."))
