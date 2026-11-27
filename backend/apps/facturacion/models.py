from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Sum

from apps.clientes.models import Cliente
from apps.core.models import AuditableModel

from .services.iva import ErrorIVA, calcular_iva, redondear, validar_desglose
from .services.sifen import validar_cdc

CERO = Decimal("0")


class Moneda(models.TextChoices):
    PYG = "PYG", "Guaraníes"
    USD = "USD", "Dólares estadounidenses"


def _monto(**kw):
    return models.DecimalField(max_digits=18, decimal_places=2, default=CERO, **kw)


class OrdenCompra(AuditableModel):
    """Orden de Compra emitida por un profesional independiente o una pyme."""

    class Estado(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        PARCIAL = "parcial", "Facturada parcialmente"
        FACTURADA = "facturada", "Facturada"
        ANULADA = "anulada", "Anulada"

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="ordenes_compra")
    numero = models.CharField("N° de OC", max_length=40)
    fecha = models.DateField()
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.PYG)
    monto_total = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    obra_proyecto = models.CharField(max_length=200, blank=True)
    archivo = models.FileField(upload_to="oc/%Y/%m/", blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ordenes_compra"
        ordering = ["-fecha", "-id"]
        constraints = [models.UniqueConstraint(fields=["cliente", "numero"], name="oc_numero_unico_por_cliente")]

    def __str__(self):
        return f"OC {self.numero} ({self.cliente.razon_social})"

    @property
    def monto_facturado(self) -> Decimal:
        if not self.pk:
            return CERO
        return self.facturas.exclude(estado=Factura.Estado.ANULADA).aggregate(s=Sum("total"))["s"] or CERO

    @property
    def saldo_disponible(self) -> Decimal:
        return self.monto_total - self.monto_facturado

    def actualizar_estado(self):
        if self.estado == self.Estado.ANULADA:
            return
        facturado = self.monto_facturado
        nuevo = (self.Estado.ABIERTA if facturado == 0
                 else self.Estado.FACTURADA if facturado >= self.monto_total else self.Estado.PARCIAL)
        if nuevo != self.estado:
            self.estado = nuevo
            self.save(update_fields=["estado", "actualizado_en"])

    def clean(self):
        if self.cliente_id and not self.cliente.requiere_orden_compra:
            raise ValidationError({"cliente": "Los clientes particulares no manejan Orden de Compra."})


class Factura(AuditableModel):
    class Condicion(models.TextChoices):
        CONTADO = "contado", "Contado"
        CREDITO = "credito", "Crédito"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente de cobro"
        PARCIAL = "parcial", "Cobro parcial"
        PAGADA = "pagada", "Pagada"
        ANULADA = "anulada", "Anulada"

    class EstadoSifen(models.TextChoices):
        BORRADOR = "borrador", "Borrador (no enviado)"
        ENVIADO = "enviado", "Enviado / en proceso"
        APROBADO = "aprobado", "Aprobado"
        APROBADO_OBS = "aprobado_obs", "Aprobado con observación"
        RECHAZADO = "rechazado", "Rechazado"
        CANCELADO = "cancelado", "Cancelado"

    ESTADOS_SIFEN_APROBADOS = (EstadoSifen.APROBADO, EstadoSifen.APROBADO_OBS)

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="facturas")
    orden_compra = models.ForeignKey(OrdenCompra, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name="facturas")

    # --- Numeración (001-001-0000001) y timbrado ---
    timbrado = models.CharField(max_length=8, validators=[RegexValidator(r"^\d{8}$", "El timbrado tiene 8 dígitos.")])
    establecimiento = models.CharField(max_length=3, validators=[RegexValidator(r"^\d{3}$", "3 dígitos.")])
    punto_expedicion = models.CharField(max_length=3, validators=[RegexValidator(r"^\d{3}$", "3 dígitos.")])
    numero = models.CharField(max_length=7, validators=[RegexValidator(r"^\d{7}$", "7 dígitos.")])

    # --- SIFEN ---
    cdc = models.CharField("CDC", max_length=44, blank=True, db_index=True)
    estado_sifen = models.CharField(max_length=12, choices=EstadoSifen.choices, default=EstadoSifen.BORRADOR)
    sifen_respuesta = models.CharField(max_length=255, blank=True, help_text="Código y mensaje devuelto por la SET.")
    sifen_fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    kude_url = models.URLField("URL del KuDE", blank=True)

    # --- Condiciones ---
    fecha_emision = models.DateField()
    condicion = models.CharField(max_length=8, choices=Condicion.choices)
    plazo_dias = models.PositiveSmallIntegerField(default=0)
    fecha_vencimiento = models.DateField()
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.PYG)
    tipo_cambio = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Guaraníes por dólar. Obligatorio en facturas USD (límite de crédito y liquidación de IVA en Gs.).",
    )
    tasa_interes_anual = models.DecimalField(
        max_digits=6, decimal_places=3, default=CERO,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Tasa compensatoria pactada (% anual). Se usará en la etapa de intereses por mora.",
    )

    # --- Totales: se calculan desde los ítems, nunca se cargan a mano ---
    gravada_10 = _monto()
    iva_10 = _monto()
    gravada_5 = _monto()
    iva_5 = _monto()
    exenta = _monto()
    total = _monto()
    porcentaje_retencion_iva = models.DecimalField(
        max_digits=5, decimal_places=2, default=CERO, validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Si el cliente es agente de retención: % del IVA que retiene (verificar resolución SET vigente).",
    )
    retencion_iva = _monto()
    saldo = _monto(help_text="Saldo pendiente de cobro (se actualizará con el módulo de cobranzas).")

    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    motivo_anulacion = models.CharField(max_length=255, blank=True)
    observaciones = models.TextField(blank=True)
    creado_por = models.ForeignKey("core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    CAMPOS_AUDITADOS = (
        "estado", "fecha_vencimiento", "plazo_dias", "condicion", "total", "saldo", "orden_compra_id",
        "estado_sifen", "cdc", "tasa_interes_anual", "porcentaje_retencion_iva", "motivo_anulacion",
    )

    class Meta:
        db_table = "facturas"
        ordering = ["-fecha_emision", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["timbrado", "establecimiento", "punto_expedicion", "numero"],
                                    name="factura_numero_unico"),
            models.UniqueConstraint(fields=["cdc"], condition=~models.Q(cdc=""), name="factura_cdc_unico"),
            models.CheckConstraint(
                condition=models.Q(total=models.F("gravada_10") + models.F("iva_10") + models.F("gravada_5")
                                   + models.F("iva_5") + models.F("exenta")),
                name="factura_total_cuadra",
            ),
            models.CheckConstraint(condition=~models.Q(moneda="USD") | models.Q(tipo_cambio__isnull=False),
                                   name="factura_usd_con_tipo_cambio"),
        ]
        indexes = [models.Index(fields=["estado", "fecha_vencimiento"]), models.Index(fields=["cliente", "estado"])]

    def __str__(self):
        return f"{self.numero_completo} - {self.cliente.razon_social}"

    @property
    def numero_completo(self) -> str:
        return f"{self.establecimiento}-{self.punto_expedicion}-{self.numero}"

    @property
    def iva_total(self) -> Decimal:
        return self.iva_10 + self.iva_5

    @property
    def aprobada_sifen(self) -> bool:
        return self.estado_sifen in self.ESTADOS_SIFEN_APROBADOS

    # ------------------------------------------------------------------ #
    def calcular_vencimiento(self):
        """Contado: vence el día de emisión. Crédito: emisión + plazo."""
        if self.condicion == self.Condicion.CONTADO:
            self.plazo_dias = 0
        if self.fecha_emision:
            self.fecha_vencimiento = self.fecha_emision + timedelta(days=self.plazo_dias)

    def recalcular_totales(self):
        """Suma los ítems por tasa de IVA y valida el desglose resultante."""
        acum = {10: [CERO, CERO, 0], 5: [CERO, CERO, 0], 0: [CERO, CERO, 0]}
        for it in self.items.all():
            a = acum[int(it.tasa_iva)]
            a[0] += it.base_imponible
            a[1] += it.iva
            a[2] += 1
        self.gravada_10, self.iva_10 = acum[10][0], acum[10][1]
        self.gravada_5, self.iva_5 = acum[5][0], acum[5][1]
        self.exenta = acum[0][0]
        try:
            validar_desglose(self.gravada_10, self.iva_10, 10, self.moneda, acum[10][2])
            validar_desglose(self.gravada_5, self.iva_5, 5, self.moneda, acum[5][2])
        except ErrorIVA as e:
            raise ValidationError({"items": str(e)})
        self.total = self.gravada_10 + self.iva_10 + self.gravada_5 + self.iva_5 + self.exenta
        self.retencion_iva = redondear(self.iva_total * self.porcentaje_retencion_iva / 100, self.moneda)
        self.saldo = self.total

    def total_en_guaranies(self, monto=None) -> Decimal:
        monto = self.total if monto is None else monto
        return monto if self.moneda == Moneda.PYG else redondear(monto * self.tipo_cambio, "PYG")

    # ------------------------------------------------------------------ #
    def clean(self):
        """Reglas de emisión. Se aplican al crear y al cambiar cliente/condición/plazo/OC."""
        errores = {}
        c = self.cliente if self.cliente_id else None
        if c is None:
            return
        revisar = self._state.adding or self._cambio_en("cliente_id", "condicion", "plazo_dias", "orden_compra_id")

        if revisar:
            # Orden de Compra según tipo de cliente
            if not c.requiere_orden_compra and self.orden_compra_id:
                errores["orden_compra"] = "Los clientes particulares no manejan Orden de Compra."
            elif c.requiere_orden_compra and not self.orden_compra_id:
                errores["orden_compra"] = f"El N° de OC es obligatorio para clientes {c.get_tipo_display().lower()}."
            elif self.orden_compra_id:
                oc = self.orden_compra
                if oc.cliente_id != c.pk:
                    errores["orden_compra"] = "La OC pertenece a otro cliente."
                elif oc.estado == OrdenCompra.Estado.ANULADA:
                    errores["orden_compra"] = "La OC está anulada."
                elif oc.moneda != self.moneda:
                    errores["orden_compra"] = "La moneda de la factura no coincide con la de la OC."

            # Condición de venta y plazo
            if self.condicion == self.Condicion.CREDITO:
                if c.condicion_pago != Cliente.CondicionPago.CREDITO:
                    errores["condicion"] = "El cliente no tiene crédito habilitado; facture al contado."
                elif not 0 < self.plazo_dias <= (c.plazo_dias or 0):
                    errores["plazo_dias"] = f"El plazo debe estar entre 1 y {c.plazo_dias} días (pactado con el cliente)."
            elif self.plazo_dias:
                errores["plazo_dias"] = "Una venta al contado no lleva plazo."

        if self.moneda == Moneda.USD and not self.tipo_cambio:
            errores["tipo_cambio"] = "Indique el tipo de cambio para facturas en USD."
        if self.porcentaje_retencion_iva and c.tipo == Cliente.Tipo.PARTICULAR:
            errores["porcentaje_retencion_iva"] = "Un consumidor final no es agente de retención."
        if self.cdc and not validar_cdc(self.cdc):
            errores["cdc"] = "CDC inválido: deben ser 44 dígitos con dígito verificador correcto."
        if self.aprobada_sifen and not self.cdc:
            errores["cdc"] = "Un documento aprobado por SIFEN debe tener CDC."
        if self.estado == self.Estado.ANULADA and not self.motivo_anulacion:
            errores["motivo_anulacion"] = "Indique el motivo de la anulación."
        if errores:
            raise ValidationError(errores)

    def validar_limites(self):
        """Límite de crédito (en Gs.) y saldo disponible de la OC. Llamar con los totales ya calculados."""
        if self.condicion == self.Condicion.CREDITO:
            abiertas = (Factura.objects.filter(cliente_id=self.cliente_id, condicion=self.Condicion.CREDITO,
                                               estado__in=[self.Estado.PENDIENTE, self.Estado.PARCIAL])
                        .exclude(pk=self.pk))
            usado = sum((f.total_en_guaranies(f.saldo) for f in abiertas), CERO)
            exposicion = usado + self.total_en_guaranies()
            if exposicion > self.cliente.limite_credito:
                raise ValidationError({"total": (
                    f"Supera el límite de crédito: límite Gs. {self.cliente.limite_credito:,.0f}, "
                    f"deuda abierta Gs. {usado:,.0f}, esta factura Gs. {self.total_en_guaranies():,.0f}."
                ).replace(",", ".")})
        if self.orden_compra_id:
            disponible = self.orden_compra.monto_total - (
                self.orden_compra.facturas.exclude(estado=self.Estado.ANULADA).exclude(pk=self.pk)
                .aggregate(s=Sum("total"))["s"] or CERO)
            if self.total > disponible:
                raise ValidationError({"orden_compra": f"El total excede el saldo disponible de la OC ({disponible})."})

    def _cambio_en(self, *campos) -> bool:
        previo = type(self).objects.filter(pk=self.pk).values(*campos).first()
        return previo is None or any(previo[c] != getattr(self, c) for c in campos)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previo = type(self).objects.filter(pk=self.pk).values(
                "estado_sifen", "total", "cliente_id", "fecha_emision", "moneda").first()
            if previo and previo["estado_sifen"] in self.ESTADOS_SIFEN_APROBADOS and any(
                    previo[k] != getattr(self, k) for k in ("total", "cliente_id", "fecha_emision", "moneda")):
                raise ValidationError("Documento aprobado por SIFEN: no se puede modificar; emita nota de crédito/débito.")
        if self._state.adding or self._cambio_en("plazo_dias", "condicion", "fecha_emision"):
            self.calcular_vencimiento()
        self.full_clean()
        super().save(*args, **kwargs)


class ItemFactura(models.Model):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name="items")
    codigo = models.CharField(max_length=40, blank=True)
    descripcion = models.CharField(max_length=250, help_text="Ej.: Varilla conformada Ø12 mm x 12 m")
    unidad = models.CharField(max_length=10, default="UNI", help_text="UNI, KG, TN, BARRA, ML…")
    cantidad = models.DecimalField(max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    precio_unitario = models.DecimalField(max_digits=18, decimal_places=4, validators=[MinValueValidator(0)])
    descuento = models.DecimalField(max_digits=18, decimal_places=2, default=CERO, validators=[MinValueValidator(0)])
    tasa_iva = models.PositiveSmallIntegerField(choices=[(10, "10%"), (5, "5%"), (0, "Exento")], default=10)
    precio_incluye_iva = models.BooleanField(
        default=True, help_text="En Paraguay el precio se expresa IVA incluido: el IVA se extrae, no se suma.")
    base_imponible = models.DecimalField(max_digits=18, decimal_places=2, default=CERO, editable=False)
    iva = models.DecimalField(max_digits=18, decimal_places=2, default=CERO, editable=False)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=CERO, editable=False)

    class Meta:
        db_table = "facturas_items"

    def calcular(self):
        bruto = self.cantidad * self.precio_unitario - self.descuento
        if bruto < 0:
            raise ValidationError({"descuento": "El descuento supera el importe del ítem."})
        try:
            d = calcular_iva(bruto, self.tasa_iva, self.factura.moneda, self.precio_incluye_iva)
        except ErrorIVA as e:
            raise ValidationError({"tasa_iva": str(e)})
        self.base_imponible, self.iva, self.total = d.base_imponible, d.iva, d.total

    def save(self, *args, **kwargs):
        if self.factura.aprobada_sifen:
            raise ValidationError("Documento aprobado por SIFEN: los ítems no se pueden modificar.")
        self.calcular()
        super().save(*args, **kwargs)
