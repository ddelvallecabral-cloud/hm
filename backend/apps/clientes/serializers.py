from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = Cliente
        fields = [
            "id", "ruc", "razon_social", "tipo", "tipo_display",
            "condicion_pago", "plazo_dias", "limite_credito", "requiere_orden_compra",
            "contacto_cobranza", "telefono_cobranza", "email_cobranza", "direccion", "ciudad", "acepta_whatsapp",
            "activo", "creado_en", "actualizado_en",
        ]
        read_only_fields = ["requiere_orden_compra", "creado_en", "actualizado_en"]

    def validate(self, attrs):
        """Reutiliza Cliente.clean() para que las reglas estén en un solo lugar."""
        instancia = Cliente(**{**self._valores_actuales(), **attrs})
        try:
            instancia.clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        return attrs

    def _valores_actuales(self):
        if not self.instance:
            return {}
        return {f: getattr(self.instance, f) for f in ("ruc", "tipo", "condicion_pago", "plazo_dias", "limite_credito")}
