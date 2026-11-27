"""Cobranzas: pagos, su aplicación a facturas y gestiones de cobro."""
from datetime import time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.core.models import AuditableModel
from apps.facturacion.models import Factura, Moneda

CERO = Decimal("0")


class Pago(AuditableModel):
    """Recibo de dinero de un cliente. Puede aplicarse a una o varias facturas;
    lo no aplicado queda como saldo a favor del cliente (`monto_sin_aplicar`)."""

    class Medio(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia bancaria / SIPAP"
        CHEQUE = "cheque", "Cheque al día"
        CHEQUE_DIFERIDO = "cheque_diferido", "Cheque de pago diferido"
        TARJETA = "tarjeta", "Tarjeta de débito/crédito"
        BILLETERA = "billetera", "Billetera electrónica / QR"
        RETENCION = "retencion", "Comprobante de retención de IVA"

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="pagos")
    fecha = models.DateField(help_text="Fecha valor del cobro (cheque diferido: fecha de acreditación).")
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.PYG)
    monto = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    medio = models.CharField(max_length=16, choices=Medio.choices)
    referencia = models.CharField(max_length=80, blank=True, help_text="N° de transferencia, cheque o comprobante.")
    banco = models.CharField(max_length=80, blank=True)
    numero_recibo = models.CharField(max_length=20, blank=True)
    observaciones = models.CharField(max_length=255, blank=True)
    registrado_por = models.ForeignKey("core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    CAMPOS_AUDITADOS = ("cliente_id", "fecha", "moneda", "monto", "medio", "referencia", "anulado", "motivo_anulacion")

    class Meta:
        db_table = "pagos"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Pago #{self.pk} {self.cliente.razon_social} {self.moneda} {self.monto}"

    @property
    def monto_aplicado(self) -> Decimal:
        if not self.pk:
            return CERO
        return self.aplicaciones.aggregate(s=Sum("monto"))["s"] or CERO

    @property
    def monto_sin_aplicar(self) -> Decimal:
        return CERO if self.anulado else self.monto - self.monto_aplicado

    def clean(self):
        if self.medio in (self.Medio.CHEQUE, self.Medio.CHEQUE_DIFERIDO, self.Medio.TRANSFERENCIA) \
                and not self.referencia:
            raise ValidationError({"referencia": "Indique el N° de cheque o de transferencia."})
        if self.anulado and not self.motivo_anulacion:
            raise ValidationError({"motivo_anulacion": "Indique el motivo de la anulación."})


class AplicacionPago(models.Model):
    """Imputación de (parte de) un pago a una factura: concilia pagos parciales."""

    pago = models.ForeignKey(Pago, on_delete=models.CASCADE, related_name="aplicaciones")
    factura = models.ForeignKey(Factura, on_delete=models.PROTECT, related_name="aplicaciones")
    monto = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pagos_aplicaciones"
        ordering = ["id"]

    def __str__(self):
        return f"{self.monto} de pago #{self.pago_id} → {self.factura.numero_completo}"

    def clean(self):
        if self.pago.moneda != self.factura.moneda:
            raise ValidationError("La moneda del pago debe coincidir con la de la factura.")
        if self.pago.cliente_id != self.factura.cliente_id:
            raise ValidationError("El pago y la factura deben ser del mismo cliente.")


class ParametrosCobranza(AuditableModel):
    """Criterios de buenas prácticas de cobranza extrajudicial (registro único).

    NO bloquean ninguna gestión: si una gestión se sale de estos criterios, el
    sistema genera alertas y la deja pendiente de revisión por tesorería, que
    decide qué se comunica finalmente al cliente. Valores por defecto prudentes;
    revisarlos con la asesoría legal (Ley 1334/98 de Defensa del Consumidor).
    """

    hora_inicio = models.TimeField(default=time(8, 0))
    hora_fin = models.TimeField(default=time(19, 0))
    permitir_sabados = models.BooleanField(default=True)
    hora_fin_sabado = models.TimeField(default=time(12, 0))
    permitir_domingos_feriados = models.BooleanField(default=False)
    max_contactos_semana = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(14)],
        help_text="A partir de este número de contactos en 7 días corridos se genera una alerta.")
    dias_aviso_vencimiento = models.PositiveSmallIntegerField(
        default=5, help_text="Con cuántos días de anticipación se alerta un vencimiento próximo.")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "parametros_cobranza"
        verbose_name = verbose_name_plural = "Parámetros de cobranza"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj = cls.objects.filter(pk=1).first()
        return obj or cls.objects.create(pk=1)


class Feriado(models.Model):
    fecha = models.DateField(unique=True)
    descripcion = models.CharField(max_length=120)

    class Meta:
        db_table = "feriados"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} {self.descripcion}"


class GestionCobro(AuditableModel):
    """Registro de cada acción de cobro: llamadas, correos, mensajes, visitas, promesas de pago.

    Enfoque NO restrictivo: el sistema nunca impide registrar una gestión. Evalúa
    buenas prácticas de cobranza no intimidatoria y, si encuentra algo para
    revisar, guarda `alertas` y deja la gestión "pendiente de revisión" para que
    tesorería decida (aprobar tal cual o modificar el mensaje final):
      * horario y días recomendados (sin domingos ni feriados);
      * frecuencia de contactos con el mismo cliente;
      * contacto por WhatsApp/SMS sin consentimiento registrado;
      * expresiones que pueden resultar intimidatorias o involucrar a terceros.
    """

    class Tipo(models.TextChoices):
        LLAMADA = "llamada", "Llamada telefónica"
        EMAIL = "email", "Correo electrónico"
        WHATSAPP = "whatsapp", "WhatsApp / SMS"
        VISITA = "visita", "Visita"
        CARTA = "carta", "Nota / carta"
        NOTA_INTERNA = "nota_interna", "Nota interna (sin contacto)"

    class Resultado(models.TextChoices):
        CONTACTADO = "contactado", "Contactado"
        NO_CONTESTA = "no_contesta", "No contesta"
        PROMESA_PAGO = "promesa_pago", "Promesa de pago"
        RECLAMO = "reclamo", "Reclamo / disputa de la factura"
        INFORMA_PAGO = "informa_pago", "Informa pago realizado"
        DERIVADO_LEGAL = "derivado_legal", "Derivado a asesoría legal"

    class Destinatario(models.TextChoices):
        TITULAR = "titular", "Titular o representante del cliente"
        CONTACTO_AUTORIZADO = "contacto_autorizado", "Contacto de cobranza autorizado"

    class Revision(models.TextChoices):
        NO_REQUIERE = "no_requiere", "Sin observaciones"
        PENDIENTE = "pendiente", "Pendiente de revisión por tesorería"
        APROBADA = "aprobada", "Aprobada por tesorería"
        MODIFICADA = "modificada", "Mensaje modificado por tesorería"

    # Expresiones que generan alerta (no bloquean). Ampliar con la asesoría legal.
    EXPRESIONES_SENSIBLES = (
        "cárcel", "carcel", "preso", "presa", "prisión", "prision", "denuncia penal", "policía", "policia",
        "embargo inmediato", "vamos a embargar", "le embargaremos", "escrache", "publicaremos su deuda",
        "avisaremos a su empleador", "su empleador", "su familia", "sus vecinos", "ladrón", "ladron",
        "estafador", "sinvergüenza", "sinverguenza", "delincuente", "inútil", "inutil", "último aviso", "ultimo aviso",
    )

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="gestiones")
    facturas = models.ManyToManyField(Factura, blank=True, related_name="gestiones")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    fecha_hora = models.DateTimeField(default=timezone.now)
    destinatario = models.CharField(max_length=20, choices=Destinatario.choices, default=Destinatario.TITULAR)
    resultado = models.CharField(max_length=15, choices=Resultado.choices, blank=True)
    mensaje = models.TextField(blank=True, help_text="Texto propuesto/enviado o resumen de la conversación.")
    promesa_fecha = models.DateField(null=True, blank=True)
    promesa_monto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True,
                                        validators=[MinValueValidator(Decimal("0.01"))])
    promesa_cumplida = models.BooleanField(null=True, blank=True, help_text="Vacío = aún no evaluada.")
    proxima_accion = models.DateField(null=True, blank=True)
    cobrador = models.ForeignKey("core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="gestiones")

    # Alertas y decisión de tesorería
    alertas = models.JSONField(default=list, blank=True)
    revision = models.CharField(max_length=12, choices=Revision.choices, default=Revision.NO_REQUIERE)
    mensaje_final = models.TextField(blank=True, help_text="Texto que tesorería decidió comunicar al cliente.")
    comentario_revision = models.CharField(max_length=255, blank=True)
    revisada_por = models.ForeignKey("core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    CAMPOS_AUDITADOS = ("tipo", "fecha_hora", "resultado", "mensaje", "promesa_fecha", "promesa_monto",
                        "promesa_cumplida", "proxima_accion", "revision", "mensaje_final", "comentario_revision")

    class Meta:
        db_table = "gestiones_cobro"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.cliente.razon_social} ({self.fecha_hora:%d/%m/%Y %H:%M})"

    @property
    def es_contacto(self) -> bool:
        return self.tipo != self.Tipo.NOTA_INTERNA

    # ------------------------------------------------------------------ #
    def evaluar_alertas(self) -> list[dict]:
        """Devuelve alertas de buenas prácticas. Nunca lanza errores."""
        alertas = []

        def alerta(codigo, texto, sugerencia):
            alertas.append({"codigo": codigo, "mensaje": texto, "sugerencia": sugerencia})

        texto = (self.mensaje or "").lower()
        sensibles = sorted({e for e in self.EXPRESIONES_SENSIBLES if e in texto})
        if sensibles:
            alerta("expresiones", "El mensaje contiene expresiones que pueden resultar intimidatorias o involucrar "
                                  "a terceros: " + ", ".join(sensibles) + ".",
                   "Informe el atraso con datos concretos (factura, monto, vencimiento) y ofrezca opciones de pago. "
                   "Use la recomendación sugerida para el tramo de atraso.")
        if self.cliente_id and self.tipo == self.Tipo.WHATSAPP and not self.cliente.acepta_whatsapp:
            alerta("whatsapp", "El cliente no tiene registrado consentimiento para WhatsApp/SMS.",
                   "Prefiera correo o llamada, o registre el consentimiento en la ficha del cliente.")
        if self.cliente_id and self.es_contacto and self.fecha_hora:
            p = ParametrosCobranza.get()
            local = timezone.localtime(self.fecha_hora)
            hora, dia = local.time(), local.weekday()
            feriado = Feriado.objects.filter(fecha=local.date()).exists()
            horario = f"{p.hora_inicio:%H:%M} a {p.hora_fin:%H:%M} (sábados hasta {p.hora_fin_sabado:%H:%M})"
            if (dia == 6 or feriado) and not p.permitir_domingos_feriados:
                alerta("dia", "Contacto en domingo o feriado.", f"Se recomienda contactar en días hábiles, {horario}.")
            elif dia == 5 and (not p.permitir_sabados or not p.hora_inicio <= hora <= p.hora_fin_sabado):
                alerta("horario", "Contacto fuera del horario recomendado para sábados.", f"Horario sugerido: {horario}.")
            elif dia < 5 and not p.hora_inicio <= hora <= p.hora_fin:
                alerta("horario", "Contacto fuera del horario recomendado.", f"Horario sugerido: {horario}.")
            recientes = (GestionCobro.objects.filter(cliente_id=self.cliente_id,
                                                     fecha_hora__gt=self.fecha_hora - timedelta(days=7),
                                                     fecha_hora__lte=self.fecha_hora)
                         .exclude(tipo=self.Tipo.NOTA_INTERNA).exclude(pk=self.pk).count())
            if recientes >= p.max_contactos_semana:
                alerta("frecuencia", f"Ya hubo {recientes} contactos con este cliente en los últimos 7 días.",
                       "Espaciar los contactos evita que se perciba como hostigamiento; "
                       "considere una nota interna y retomar en unos días.")
        return alertas

    def clean(self):
        # Sólo integridad de datos: las buenas prácticas generan alertas, no errores.
        errores = {}
        if self.resultado == self.Resultado.PROMESA_PAGO and not (self.promesa_fecha and self.promesa_monto):
            errores["promesa_fecha"] = "Una promesa de pago requiere fecha y monto."
        if self.promesa_fecha and self.fecha_hora and self.promesa_fecha < timezone.localtime(self.fecha_hora).date():
            errores["promesa_fecha"] = "La fecha prometida no puede ser anterior a la gestión."
        if self.revision in (self.Revision.APROBADA, self.Revision.MODIFICADA) and not self.revisada_por_id:
            errores["revision"] = "La revisión debe registrar quién la hizo."
        if self.revision == self.Revision.MODIFICADA and not self.mensaje_final:
            errores["mensaje_final"] = "Indique el mensaje final que se comunicará."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        if self._state.adding:
            self.alertas = self.evaluar_alertas()
            self.revision = self.Revision.PENDIENTE if self.alertas else self.Revision.NO_REQUIERE
        super().save(*args, **kwargs)
