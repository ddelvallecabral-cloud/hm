from rest_framework import serializers

from .models import AlertaTasa, TasaReferenciaBCP


class TasaReferenciaBCPSerializer(serializers.ModelSerializer):
    class Meta:
        model = TasaReferenciaBCP
        fields = "__all__"
        read_only_fields = ["creado_en", "actualizado_en"]


class AlertaTasaSerializer(serializers.ModelSerializer):
    factura_numero = serializers.CharField(source="factura.numero_completo", read_only=True)
    cliente = serializers.CharField(source="factura.cliente.razon_social", read_only=True)

    class Meta:
        model = AlertaTasa
        fields = "__all__"
        read_only_fields = [f for f in ("factura", "tipo", "moneda", "tasa_pactada_anual", "tope_aplicado_anual",
                                        "periodo_tope", "mensaje", "creado_en")]
