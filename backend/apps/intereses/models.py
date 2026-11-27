"""Intereses por mora: tasas máximas del BCP y alertas de ajuste de tasa.

Base legal (ver README, sección "Intereses por mora"):
- Código Civil, Art. 475: los intereses moratorios no pueden superar las tasas
  máximas fijadas por el BCP; la estipulación que las exceda es nula en el exceso.
- Ley N° 489/95 Orgánica del BCP, Art. 44 (mod. Ley N° 2339/03): desde la mora,
  el interés compensatorio pactado pasa a ser moratorio y no puede superar la
  tasa originalmente pactada. No se admite la capitalización de intereses.
"""
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import AuditableModel
from apps.facturacion.models import Factura, Moneda


class TasaReferenciaBCP(AuditableModel):
    """Tasa máxima anual (límite de usura) publicada por el BCP para un mes y una moneda.

    Ninguna tasa está fija en el código: un administrador carga cada mes el
    valor publicado por el BCP indicando la resolución o comunicado de origen.
    """

    anio = models.PositiveSmallIntegerField("año", validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    mes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    tasa_maxima_anual = models.DecimalField(
        max_digits=6, decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001")), MaxValueValidator(Decimal("100"))],
        help_text="Porcentaje anual, p. ej. 27.260",
    )
    fuente = models.CharField(max_length=255, help_text="Resolución o comunicado del BCP (y enlace si lo hay).")
    observaciones = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tasas_referencia_bcp"
        verbose_name = "tasa de referencia BCP"
        verbose_name_plural = "tasas de referencia BCP"
        ordering = ["-anio", "-mes", "moneda"]
        constraints = [models.UniqueConstraint(fields=["anio", "mes", "moneda"], name="tasa_bcp_unica_por_mes_y_moneda")]

    def __str__(self):
        return f"{self.mes:02d}/{self.anio} {self.moneda}: {self.tasa_maxima_anual}%"


class AlertaTasa(models.Model):
    """Registro de cada factura cuya tasa pactada se ajustó al tope legal (o no tenía tope cargado)."""

    class Tipo(models.TextChoices):
        AJUSTE_TOPE = "ajuste_tope", "Tasa pactada ajustada al tope legal"
        TASA_MES_ANTERIOR = "tasa_mes_anterior", "Se usó la tasa BCP de un mes anterior"

    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name="alertas_tasa")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    tasa_pactada_anual = models.DecimalField(max_digits=6, decimal_places=3)
    tope_aplicado_anual = models.DecimalField(max_digits=6, decimal_places=3)
    periodo_tope = models.CharField(max_length=7, help_text="MM/AAAA de la tasa BCP usada.")
    mensaje = models.CharField(max_length=300)
    revisada = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alertas_tasa"
        ordering = ["-creado_en"]
        constraints = [models.UniqueConstraint(fields=["factura", "tipo", "periodo_tope"], name="alerta_tasa_unica")]

    def __str__(self):
        return f"{self.factura.numero_completo}: {self.get_tipo_display()}"
