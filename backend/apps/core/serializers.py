from rest_framework import serializers

from .models import AuditLog, Usuario


class UsuarioActualSerializer(serializers.ModelSerializer):
    es_tesorero = serializers.BooleanField(read_only=True)
    es_administrador = serializers.BooleanField(read_only=True)

    class Meta:
        model = Usuario
        fields = ["id", "username", "first_name", "last_name", "email", "rol", "es_tesorero", "es_administrador"]


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"
