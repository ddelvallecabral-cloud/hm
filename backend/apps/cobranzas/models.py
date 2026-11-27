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
    """Límites para una cobranza extrajudicial no intimidatoria (registro único).

    Valores por defecto prudentes; revisarlos con la asesoría legal de la empresa
    (Ley 1334/98 de Defensa del Consumidor y normativa complementaria).
    """

    hora_inicio = models.TimeField(default=time(8, 0))
    hora_fin = models.TimeField(default=time(19, 0))
    permitir_sabados = models.BooleanField(default=True)
    hora_fin_sabado = models.TimeField(default=time(12, 0))
    permitir_domingos_feriados = models.BooleanField(default=False)
    max_contactos_semana = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(14)],
        help_text="Máximo de contactos con el mismo cliente en 7 días corridos.")
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

    Validaciones de cobranza no intimidatoria:
      * sólo en el horario y días permitidos (no domingos ni feriados por defecto);
      * frecuencia máxima de contactos por semana con el mismo cliente;
      * sólo con el titular o un contacto autorizado (nunca terceros: familia, empleador, vecinos);
      * WhatsApp/SMS sólo con consentimiento del cliente;
      * el mensaje no puede contener amenazas, falsedades sobre consecuencias legales ni insultos.
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

    # Lista mínima; ampliarla con la asesoría legal.
    EXPRESIONES_PROHIBIDAS = (
        "cárcel", "carcel", "preso", "presa", "prisión", "prision", "denuncia penal", "policía", "policia",
        "embargo inmediato", "vamos a embargar", "le embargaremos", "escrache", "publicaremos su deuda",
        "avisaremos a su empleador", "su empleador", "su familia", "sus vecinos", "ladrón", "ladron",
        "estafador", "sinvergüenza", "sinverguenza", "delincuente", "inútil", "inutil",
    )

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="gestiones")
    facturas = models.ManyToManyField(Factura, blank=True, related_name="gestiones")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    fecha_hora = models.DateTimeField(default=timezone.now)
    destinatario = models.CharField(max_length=20, choices=Destinatario.choices, default=Destinatario.TITULAR)
    resultado = models.CharField(max_length=15, choices=Resultado.choices, blank=True)
    mensaje = models.TextField(blank=True, help_text="Texto enviado o resumen de la conversación.")
    promesa_fecha = models.DateField(null=True, blank=True)
    promesa_monto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True,
                                        validators=[MinValueValidator(Decimal("0.01"))])
    promesa_cumplida = models.BooleanField(null=True, blank=True, help_text="Vacío = aún no evaluada.")
    proxima_accion = models.DateField(null=True, blank=True)
    cobrador = models.ForeignKey("core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="gestiones")
    creado_en = models.DateTimeField(auto_now_add=True)

    CAMPOS_AUDITADOS = ("tipo", "fecha_hora", "resultado", "mensaje", "promesa_fecha", "promesa_monto",
                        "promesa_cumplida", "proxima_accion")

    class Meta:
        db_table = "gestiones_cobro"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.cliente.razon_social} ({self.fecha_hora:%d/%m/%Y %H:%M})"

    @property
    def es_contacto(self) -> bool:
        return self.tipo != self.Tipo.NOTA_INTERNA

    def clean(self):
        errores = {}
        texto = (self.mensaje or "").lower()
        prohibidas = sorted({e for e in self.EXPRESIONES_PROHIBIDAS if e in texto})
        if prohibidas:
            errores["mensaje"] = ("El mensaje contiene expresiones intimidatorias o que involucran a terceros, "
                                  "no permitidas en la cobranza extrajudicial: " + ", ".join(prohibidas))
        if self.resultado == self.Resultado.PROMESA_PAGO and not (self.promesa_fecha and self.promesa_monto):
            errores["promesa_fecha"] = "Una promesa de pago requiere fecha y monto."
        if self.promesa_fecha and self.fecha_hora and self.promesa_fecha < timezone.localtime(self.fecha_hora).date():
            errores["promesa_fecha"] = "La fecha prometida no puede ser anterior a la gestión."
        if self.cliente_id and self.tipo == self.Tipo.WHATSAPP and not self.cliente.acepta_whatsapp:
            errores["tipo"] = "El cliente no autorizó contacto por WhatsApp/SMS."
        if self.cliente_id and self.es_contacto and self._state.adding:
            errores.update(self._validar_horario_y_frecuencia())
        if errores:
            raise ValidationError(errores)

    def _validar_horario_y_frecuencia(self) -> dict:
        p = ParametrosCobranza.get()
        local = timezone.localtime(self.fecha_hora)
        hora, dia = local.time(), local.weekday()  # 0 = lunes
        feriado = Feriado.objects.filter(fecha=local.date()).exists()
        if (dia == 6 or feriado) and not p.permitir_domingos_feriados:
            return {"fecha_hora": "No se realizan gestiones de cobro en domingos ni feriados."}
        if dia == 5:
            if not p.permitir_sabados:
                return {"fecha_hora": "No se realizan gestiones de cobro los sábados."}
            if not p.hora_inicio <= hora <= p.hora_fin_sabado:
                return {"fecha_hora": f"Los sábados sólo de {p.hora_inicio:%H:%M} a {p.hora_fin_sabado:%H:%M}."}
        elif dia < 5 and not p.hora_inicio <= hora <= p.hora_fin:
            return {"fecha_hora": f"Horario de contacto permitido: {p.hora_inicio:%H:%M} a {p.hora_fin:%H:%M}."}
        recientes = (GestionCobro.objects.filter(cliente_id=self.cliente_id,
                                                 fecha_hora__gt=self.fecha_hora - timedelta(days=7),
                                                 fecha_hora__lte=self.fecha_hora)
                     .exclude(tipo=self.Tipo.NOTA_INTERNA).count())
        if recientes >= p.max_contactos_semana:
            return {"fecha_hora": f"Ya hubo {recientes} contactos con este cliente en los últimos 7 días "
                                  f"(máximo {p.max_contactos_semana}). Registre una nota interna o espere."}
        return {}

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
