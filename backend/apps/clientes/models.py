from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import AuditableModel

from .validators import validar_ruc


class Cliente(AuditableModel):
    class Tipo(models.TextChoices):
        PARTICULAR = "particular", "Particular (consumidor final)"
        PROFESIONAL_INDEPENDIENTE = "profesional_independiente", "Profesional independiente"
        PYME = "pyme", "Pyme / Empresa"

    class CondicionPago(models.TextChoices):
        CONTADO = "contado", "Contado"
        CREDITO = "credito", "Crédito"

    class Plazo(models.IntegerChoices):
        DIAS_30 = 30, "30 días"
        DIAS_60 = 60, "60 días"
        DIAS_90 = 90, "90 días"

    # Tipos que operan con Orden de Compra.
    TIPOS_CON_OC = (Tipo.PROFESIONAL_INDEPENDIENTE, Tipo.PYME)

    # --- Identificación ---
    ruc = models.CharField(
        "RUC", max_length=10, blank=True, validators=[validar_ruc],
        help_text="Formato número-DV. Obligatorio para profesionales y pymes; "
                  "opcional para particulares (consumidor final).",
    )
    razon_social = models.CharField(max_length=200)
    tipo = models.CharField(max_length=30, choices=Tipo.choices)

    # --- Condiciones comerciales ---
    condicion_pago = models.CharField(max_length=10, choices=CondicionPago.choices, default=CondicionPago.CONTADO)
    plazo_dias = models.PositiveSmallIntegerField(
        choices=Plazo.choices, null=True, blank=True,
        help_text="Sólo para crédito: 30, 60 o 90 días. Vacío en contado.",
    )
    limite_credito = models.DecimalField(
        max_digits=18, decimal_places=0, default=Decimal("0"), validators=[MinValueValidator(0)],
        help_text="En guaraníes (sin decimales). 0 para clientes de contado.",
    )
    requiere_orden_compra = models.BooleanField(
        default=False, editable=False,
        help_text="Se deriva del tipo: True para profesionales y pymes, False para particulares.",
    )

    # --- Contacto para cobranza ---
    contacto_cobranza = models.CharField("persona de contacto", max_length=150, blank=True)
    telefono_cobranza = models.CharField(max_length=30, blank=True)
    email_cobranza = models.EmailField(blank=True)
    direccion = models.CharField(max_length=250, blank=True)
    ciudad = models.CharField(max_length=80, blank=True)

    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes"
        ordering = ["razon_social"]
        constraints = [
            # RUC único, pero varios particulares pueden no tener RUC.
            models.UniqueConstraint(fields=["ruc"], condition=~models.Q(ruc=""), name="clientes_ruc_unico"),
            models.CheckConstraint(
                condition=models.Q(condicion_pago="contado", plazo_dias__isnull=True)
                | models.Q(condicion_pago="credito", plazo_dias__in=[30, 60, 90]),
                name="clientes_plazo_segun_condicion",
            ),
            models.CheckConstraint(condition=models.Q(limite_credito__gte=0), name="clientes_limite_no_negativo"),
        ]
        indexes = [models.Index(fields=["tipo"]), models.Index(fields=["razon_social"])]

    def __str__(self):
        return f"{self.razon_social} ({self.ruc or 'sin RUC'})"

    def clean(self):
        errores = {}
        if self.tipo in self.TIPOS_CON_OC and not self.ruc:
            errores["ruc"] = "El RUC es obligatorio para profesionales independientes y pymes."
        if self.condicion_pago == self.CondicionPago.CREDITO:
            if self.plazo_dias is None:
                errores["plazo_dias"] = "Un cliente a crédito debe tener plazo (30, 60 o 90 días)."
            if not self.limite_credito or self.limite_credito <= 0:
                errores["limite_credito"] = "Un cliente a crédito debe tener un límite de crédito mayor a 0."
        else:
            if self.plazo_dias is not None:
                errores["plazo_dias"] = "Un cliente de contado no lleva plazo de crédito."
            if self.limite_credito:
                errores["limite_credito"] = "Un cliente de contado no lleva límite de crédito."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        # La regla vive en el modelo: nunca depende de lo que envíe el frontend.
        self.requiere_orden_compra = self.tipo in self.TIPOS_CON_OC
        super().save(*args, **kwargs)
