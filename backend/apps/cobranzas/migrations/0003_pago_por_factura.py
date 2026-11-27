"""Esquema simple de pagos: cada Pago apunta a una Factura (se elimina AplicacionPago).

Migración de datos: un pago aplicado a una sola factura pasa a apuntarla; uno
aplicado a varias se divide en un pago por factura (mismos datos, monto de
cada aplicación). Los pagos sin aplicar (saldo a favor) no tienen factura en
el nuevo esquema y se eliminan: en esta etapa sólo existían datos de prueba.
"""
import django.db.models.deletion
from django.db import migrations, models


def pasar_a_pago_por_factura(apps, schema_editor):
    Pago = apps.get_model("cobranzas", "Pago")
    Aplicacion = apps.get_model("cobranzas", "AplicacionPago")
    for pago in Pago.objects.all():
        aplicaciones = list(Aplicacion.objects.filter(pago=pago).order_by("id"))
        if not aplicaciones:
            pago.delete()
            continue
        primera, resto = aplicaciones[0], aplicaciones[1:]
        for a in resto:
            Pago.objects.create(
                factura_id=a.factura_id, monto=a.monto, fecha=pago.fecha, medio=pago.medio, moneda=pago.moneda,
                referencia=pago.referencia, banco=pago.banco, numero_recibo=pago.numero_recibo,
                observaciones=pago.observaciones, registrado_por_id=pago.registrado_por_id,
                anulado=pago.anulado, motivo_anulacion=pago.motivo_anulacion,
            )
        pago.factura_id = primera.factura_id
        pago.monto = primera.monto
        pago.save(update_fields=["factura", "monto"])


class Migration(migrations.Migration):
    dependencies = [
        ("cobranzas", "0002_gestioncobro_alertas_and_more"),
        ("facturacion", "0003_alter_factura_estado"),
    ]

    operations = [
        migrations.AddField(
            model_name="pago",
            name="factura",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name="pagos", to="facturacion.factura"),
        ),
        migrations.RunPython(pasar_a_pago_por_factura, migrations.RunPython.noop),
        migrations.RemoveField(model_name="pago", name="cliente"),
        migrations.DeleteModel(name="AplicacionPago"),
        migrations.AlterField(
            model_name="pago",
            name="factura",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pagos",
                                    to="facturacion.factura"),
        ),
        migrations.AddIndex(
            model_name="pago",
            index=models.Index(fields=["factura", "anulado"], name="pagos_factura_06305d_idx"),
        ),
    ]
