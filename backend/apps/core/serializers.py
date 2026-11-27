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


class UsuarioAdminSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=10,
                                     help_text="Sólo al crear o para restablecer la contraseña.")

    class Meta:
        model = Usuario
        fields = ["id", "username", "first_name", "last_name", "email", "rol", "is_active", "last_login",
                  "date_joined", "password"]
        read_only_fields = ["last_login", "date_joined"]

    def validate(self, attrs):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Indique una contraseña inicial."})
        if attrs.get("password"):
            try:
                validate_password(attrs["password"], self.instance)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"password": e.messages})
        yo = self.context["request"].user
        if self.instance and self.instance.pk == yo.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "No puede desactivar su propio usuario."})
            if "rol" in attrs and attrs["rol"] != Usuario.Rol.ADMINISTRADOR and not yo.is_superuser:
                raise serializers.ValidationError({"rol": "No puede quitarse a sí mismo el rol de administrador."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        u = Usuario(**validated_data)
        u.set_password(password)
        u.save()
        return u

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if validated_data.get("rol") and validated_data["rol"] != Usuario.Rol.ADMINISTRADOR and not instance.is_superuser:
            instance.is_staff = False
        if password:
            instance.set_password(password)
        instance.save()
        return instance
