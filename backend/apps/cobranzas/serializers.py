from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.facturacion.models import Factura

from .models import AplicacionPago, GestionCobro, Pago


def a_drf(e: DjangoValidationError):
    return serializers.ValidationError(getattr(e, "message_dict", None) or {"detalle": e.messages})


class AplicacionPagoSerializer(serializers.ModelSerializer):
    factura_numero = serializers.CharField(source="factura.numero_completo", read_only=True)

    class Meta:
        model = AplicacionPago
        fields = ["id", "factura", "factura_numero", "monto", "creado_en"]


class ImputacionSerializer(serializers.Serializer):
    factura = serializers.PrimaryKeyRelatedField(queryset=Factura.objects.all())
    monto = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)


class PagoSerializer(serializers.ModelSerializer):
    aplicaciones = AplicacionPagoSerializer(many=True, read_only=True)
    monto_aplicado = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    monto_sin_aplicar = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    cliente_razon_social = serializers.CharField(source="cliente.razon_social", read_only=True)
    # Sólo para el alta:
    imputaciones = ImputacionSerializer(many=True, write_only=True, required=False)
    aplicar_automatico = serializers.BooleanField(
        write_only=True, required=False, default=False,
        help_text="Reparte el pago entre las facturas abiertas, de la más antigua a la más nueva.")

    class Meta:
        model = Pago
        fields = "__all__"
        read_only_fields = ["registrado_por", "anulado", "motivo_anulacion", "creado_en", "actualizado_en"]

    def validate(self, attrs):
        if attrs.get("imputaciones") and attrs.get("aplicar_automatico"):
            raise serializers.ValidationError("Use imputaciones manuales o aplicar_automatico, no ambos.")
        return attrs

    def create(self, validated_data):
        from .services import registrar_pago

        imputaciones = validated_data.pop("imputaciones", None)
        automatico = validated_data.pop("aplicar_automatico", False)
        try:
            return registrar_pago(validated_data, imputaciones, automatico, self.context["request"].user)
        except DjangoValidationError as e:
            raise a_drf(e)


class CobroContadoSerializer(serializers.Serializer):
    factura = serializers.PrimaryKeyRelatedField(queryset=Factura.objects.all())
    medio = serializers.ChoiceField(choices=Pago.Medio.choices)
    referencia = serializers.CharField(required=False, allow_blank=True, default="")
    banco = serializers.CharField(required=False, allow_blank=True, default="")
    numero_recibo = serializers.CharField(required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False)


class GestionCobroSerializer(serializers.ModelSerializer):
    cliente_razon_social = serializers.CharField(source="cliente.razon_social", read_only=True)
    cobrador_nombre = serializers.CharField(source="cobrador.username", read_only=True, default=None)

    class Meta:
        model = GestionCobro
        fields = "__all__"
        read_only_fields = ["cobrador", "creado_en", "promesa_cumplida"]

    def validate(self, attrs):
        facturas = attrs.get("facturas") or []
        cliente = attrs.get("cliente") or getattr(self.instance, "cliente", None)
        if any(f.cliente_id != cliente.pk for f in facturas):
            raise serializers.ValidationError({"facturas": "Todas las facturas deben ser del cliente gestionado."})
        return attrs

    def create(self, validated_data):
        facturas = validated_data.pop("facturas", [])
        try:
            g = GestionCobro(**validated_data)
            g.save()
        except DjangoValidationError as e:
            raise a_drf(e)
        g.facturas.set(facturas)
        return g

    def update(self, instance, validated_data):
        facturas = validated_data.pop("facturas", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        try:
            instance.save()
        except DjangoValidationError as e:
            raise a_drf(e)
        if facturas is not None:
            instance.facturas.set(facturas)
        return instance


class GestionActualizacionSerializer(GestionCobroSerializer):
    """Tras registrar una gestión sólo se completa su resultado, promesa o próxima acción."""

    class Meta(GestionCobroSerializer.Meta):
        read_only_fields = ["cobrador", "creado_en", "cliente", "tipo", "fecha_hora", "destinatario", "mensaje"]
