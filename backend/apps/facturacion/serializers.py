from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Factura, ItemFactura, OrdenCompra
from .services.emision import crear_factura


def _a_drf(e: DjangoValidationError):
    return serializers.ValidationError(getattr(e, "message_dict", None) or {"detalle": e.messages})


class OrdenCompraSerializer(serializers.ModelSerializer):
    monto_facturado = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_disponible = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = OrdenCompra
        fields = "__all__"
        read_only_fields = ["estado", "creado_en", "actualizado_en"]

    def validate(self, attrs):
        try:
            OrdenCompra(**attrs).clean()
        except DjangoValidationError as e:
            raise _a_drf(e)
        return attrs


class ItemFacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFactura
        exclude = ["factura"]
        read_only_fields = ["base_imponible", "iva", "total"]


class FacturaSerializer(serializers.ModelSerializer):
    items = ItemFacturaSerializer(many=True)
    numero_completo = serializers.CharField(read_only=True)
    iva_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    cliente_razon_social = serializers.CharField(source="cliente.razon_social", read_only=True)
    requiere_orden_compra = serializers.BooleanField(source="cliente.requiere_orden_compra", read_only=True)
    orden_compra_numero = serializers.CharField(source="orden_compra.numero", read_only=True, default=None)

    class Meta:
        model = Factura
        fields = "__all__"
        read_only_fields = [
            "gravada_10", "iva_10", "gravada_5", "iva_5", "exenta", "total", "retencion_iva", "saldo",
            "estado", "fecha_vencimiento", "motivo_anulacion", "creado_por", "creado_en", "actualizado_en",
        ]

    def create(self, validated_data):
        items = validated_data.pop("items")
        try:
            return crear_factura(validated_data, items, self.context["request"].user)
        except DjangoValidationError as e:
            raise _a_drf(e)


class FacturaActualizacionSerializer(serializers.ModelSerializer):
    """Campos modificables tras la emisión: datos SIFEN, prórroga de vencimiento, observaciones.

    Los importes, el cliente y los ítems no se editan: se anula o se emite nota de crédito.
    """

    motivo = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Factura
        fields = ["cdc", "estado_sifen", "sifen_respuesta", "sifen_fecha_aprobacion", "kude_url",
                  "fecha_vencimiento", "observaciones", "motivo"]

    def validate(self, attrs):
        f = self.instance
        nuevo_venc = attrs.get("fecha_vencimiento")
        if nuevo_venc and nuevo_venc != f.fecha_vencimiento:
            if not attrs.get("motivo"):
                raise serializers.ValidationError({"motivo": "Indique el motivo del cambio de vencimiento."})
            if nuevo_venc < f.fecha_emision:
                raise serializers.ValidationError({"fecha_vencimiento": "No puede ser anterior a la emisión."})
        return attrs

    def update(self, instance, validated_data):
        instance.motivo_auditoria = validated_data.pop("motivo", "")
        for k, v in validated_data.items():
            setattr(instance, k, v)
        try:
            instance.save()
        except DjangoValidationError as e:
            raise _a_drf(e)
        return instance
