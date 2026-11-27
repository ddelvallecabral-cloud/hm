from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from apps.facturacion.models import Factura

from .models import GestionCobro, Pago


def a_drf(e: DjangoValidationError):
    return serializers.ValidationError(getattr(e, "message_dict", None) or {"detalle": e.messages})


class PagoSerializer(serializers.ModelSerializer):
    """Pago de una factura. Al crear: factura, monto, medio y opcionalmente fecha, moneda y referencia."""

    factura_numero = serializers.CharField(source="factura.numero_completo", read_only=True)
    cliente = serializers.IntegerField(source="factura.cliente_id", read_only=True)
    cliente_razon_social = serializers.CharField(source="factura.cliente.razon_social", read_only=True)
    factura_saldo = serializers.DecimalField(source="factura.saldo", max_digits=18, decimal_places=2, read_only=True)
    factura_estado = serializers.CharField(source="factura.estado", read_only=True)
    moneda = serializers.ChoiceField(choices=[("PYG", "PYG"), ("USD", "USD")], required=False)
    fecha = serializers.DateField(required=False)

    class Meta:
        model = Pago
        fields = "__all__"
        read_only_fields = ["registrado_por", "anulado", "motivo_anulacion", "creado_en", "actualizado_en"]

    def validate(self, attrs):
        f = attrs.get("factura")
        if f and attrs.get("moneda") and attrs["moneda"] != f.moneda:
            raise serializers.ValidationError({"moneda": f"La factura está en {f.moneda}."})
        return attrs

    def create(self, validated_data):
        from .services import registrar_cobranza

        datos = dict(validated_data)
        try:
            return registrar_cobranza(datos.pop("factura"), datos.pop("monto"), datos.pop("medio"),
                                      fecha=datos.pop("fecha", None), usuario=self.context["request"].user, **datos)
        except DjangoValidationError as e:
            raise a_drf(e)


class CobroContadoSerializer(serializers.Serializer):
    factura = serializers.PrimaryKeyRelatedField(queryset=Factura.objects.all())
    medio = serializers.ChoiceField(choices=Pago.Medio.choices)
    referencia = serializers.CharField(required=False, allow_blank=True, default="")
    banco = serializers.CharField(required=False, allow_blank=True, default="")
    numero_recibo = serializers.CharField(required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False)


REVISION_READONLY = ["alertas", "revision", "mensaje_final", "comentario_revision", "revisada_por", "revisada_en"]


class GestionCobroSerializer(serializers.ModelSerializer):
    cliente_razon_social = serializers.CharField(source="cliente.razon_social", read_only=True)
    cobrador_nombre = serializers.CharField(source="cobrador.username", read_only=True, default=None)
    revisada_por_nombre = serializers.CharField(source="revisada_por.username", read_only=True, default=None)

    class Meta:
        model = GestionCobro
        fields = "__all__"
        read_only_fields = ["cobrador", "creado_en", "promesa_cumplida", *REVISION_READONLY]

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
        read_only_fields = ["cobrador", "creado_en", "cliente", "tipo", "fecha_hora", "destinatario", "mensaje",
                            *REVISION_READONLY]


class RevisionGestionSerializer(serializers.Serializer):
    """Decisión de tesorería sobre una gestión con alertas."""

    decision = serializers.ChoiceField(choices=[("aprobada", "Aprobar tal cual"), ("modificada", "Modificar el mensaje")])
    mensaje_final = serializers.CharField(required=False, allow_blank=True, default="")
    comentario = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)

    def validate(self, attrs):
        if attrs["decision"] == "modificada" and not attrs["mensaje_final"].strip():
            raise serializers.ValidationError({"mensaje_final": "Escriba el mensaje que se comunicará al cliente."})
        return attrs
