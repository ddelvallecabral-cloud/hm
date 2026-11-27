"""Carga datos de DEMOSTRACIÓN para probar el CRM (clientes, facturas, pagos).

    python manage.py cargar_demo --clave <contraseña para los usuarios demo>

Crea los usuarios demo_tesorero y demo_cobrador, tres clientes marcados
"(DEMO)" y facturas en distintos estados. Es idempotente: si ya existen
clientes demo, no hace nada. No usar en producción.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.cobranzas.services import registrar_cobranza
from apps.core.audit import contexto_auditoria
from apps.facturacion.models import OrdenCompra
from apps.facturacion.services.emision import crear_factura


class Command(BaseCommand):
    help = "Carga datos de demostración (clientes, facturas y pagos)."

    def add_arguments(self, parser):
        parser.add_argument("--clave", required=True, help="Contraseña para demo_tesorero y demo_cobrador.")

    @transaction.atomic
    def handle(self, *args, **opts):
        from django.core.management import call_command

        call_command("cargar_tasas_ejemplo", stdout=self.stdout)
        if len(opts["clave"]) < 10:
            raise CommandError("La contraseña debe tener al menos 10 caracteres.")
        if Cliente.objects.filter(razon_social__endswith="(DEMO)").exists():
            self.stdout.write("Los datos demo ya estaban cargados.")
            return
        U = get_user_model()
        tes = U.objects.create_user("demo_tesorero", password=opts["clave"], rol="tesorero", first_name="Tesorería")
        U.objects.create_user("demo_cobrador", password=opts["clave"], rol="cobrador", first_name="Cobrador")
        hoy = timezone.localdate()
        with contexto_auditoria(tes):
            juan = Cliente.objects.create(razon_social="Juan Benítez (DEMO)", tipo="particular",
                                          telefono_cobranza="0981 000 001")
            arq = Cliente.objects.create(ruc="1234567-9", razon_social="Arq. Laura Giménez (DEMO)",
                                         tipo="profesional_independiente", condicion_pago="credito", plazo_dias=30,
                                         limite_credito=80_000_000, email_cobranza="laura@example.com.py",
                                         acepta_whatsapp=True)
            pyme = Cliente.objects.create(ruc="80012345-0", razon_social="Constructora Ñandutí S.A. (DEMO)",
                                          tipo="pyme", condicion_pago="credito", plazo_dias=60,
                                          limite_credito=500_000_000, contacto_cobranza="María Rojas",
                                          email_cobranza="pagos@example.com.py")
            oc = OrdenCompra.objects.create(cliente=pyme, numero="OC-2026-118", fecha=hoy - timedelta(days=75),
                                            monto_total=200_000_000, obra_proyecto="Edificio Mburucuyá")
            n = [0]

            def fac(cliente, items, dias_atras, condicion="contado", plazo=0, **kw):
                n[0] += 1
                return crear_factura({"cliente": cliente, "timbrado": "15999999", "establecimiento": "001",
                                      "punto_expedicion": "001", "numero": f"{n[0]:07d}",
                                      "fecha_emision": hoy - timedelta(days=dias_atras), "condicion": condicion,
                                      "plazo_dias": plazo, **kw},
                                     [{"descripcion": d, "unidad": u, "cantidad": c, "precio_unitario": p}
                                      for d, u, c, p in items], usuario=tes)

            varilla = ("Varilla conformada Ø12 mm x 12 m", "BARRA")
            fac(juan, [(*varilla, 20, 98_000), ("Alambre recocido N° 18", "KG", 10, 18_500)], 0)
            fac(arq, [(*varilla, 150, 96_500)], 10, "credito", 30)                      # pendiente
            f3 = fac(arq, [("Perfil C 100x50x15x2 mm", "BARRA", 60, 210_000)], 45, "credito", 30)  # vencida
            f4 = fac(pyme, [(*varilla, 900, 95_000)], 70, "credito", 60, orden_compra=oc,
                     tasa_interes_anual=Decimal("30"))                     # vencida, pago parcial, tasa > tope
            f5 = fac(pyme, [("Malla electrosoldada 15x15 Ø6", "UNI", 120, 345_000)], 20, "credito", 60,
                     orden_compra=oc)                                                      # pago parcial
            fac(pyme, [("Chapa lisa 1,2 mm 1x2 m", "UNI", 300, Decimal("9.40"))], 5, "credito", 60, moneda="USD",
                tipo_cambio=Decimal("7650"))
            registrar_cobranza(f4, Decimal(30_000_000), "transferencia", fecha=hoy - timedelta(days=3),
                               usuario=tes, referencia="SIPAP 77120")
            registrar_cobranza(f5, Decimal(15_000_000), "cheque", fecha=hoy - timedelta(days=1),
                               usuario=tes, referencia="CH 004512", banco="Banco demo")
            del f3
        self.stdout.write(self.style.SUCCESS(
            "Datos demo cargados: usuarios demo_tesorero / demo_cobrador, 3 clientes, 6 facturas y tasas BCP de ejemplo."))
