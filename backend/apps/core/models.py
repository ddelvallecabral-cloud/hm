from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from .audit import ip_actual, resolver_usuario


class AuditLog(models.Model):
    """Bitácora inmutable: quién, cuándo, desde dónde, qué cambió y por qué."""

    class Accion(models.TextChoices):
        CREAR = "crear", "Crear"
        MODIFICAR = "modificar", "Modificar"
        ELIMINAR = "eliminar", "Eliminar"

    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey("core.Usuario", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    usuario_nombre = models.CharField(max_length=150, blank=True, help_text="Copia del username (se conserva aunque se borre el usuario).")
    ip = models.GenericIPAddressField(null=True, blank=True)
    accion = models.CharField(max_length=10, choices=Accion.choices)
    modelo = models.CharField(max_length=60, db_index=True)
    objeto_id = models.CharField(max_length=40, db_index=True)
    objeto_repr = models.CharField(max_length=200, blank=True)
    cambios = models.JSONField(default=dict, encoder=DjangoJSONEncoder, help_text='{"campo": [anterior, nuevo]}')
    motivo = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "auditoria"
        ordering = ["-fecha_hora", "-id"]
        indexes = [models.Index(fields=["modelo", "objeto_id"])]

    def __str__(self):
        return f"{self.fecha_hora:%Y-%m-%d %H:%M} {self.usuario_nombre or 'sistema'} {self.accion} {self.modelo}#{self.objeto_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("La bitácora de auditoría no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La bitácora de auditoría no se puede eliminar.")


def _valor(v):
    # Decimales y fechas como texto para que el JSON sea legible y exacto.
    return None if v is None else (v if isinstance(v, (bool, int, str)) else str(v))


class AuditableModel(models.Model):
    """Mixin: registra en AuditLog cada alta, modificación y baja.

    - `CAMPOS_AUDITADOS`: campos a comparar (vacío = todos los campos concretos).
    - Antes de `save()` puede asignarse `obj.motivo_auditoria = "..."`;
      queda guardado junto al cambio (p. ej. "cliente pidió prórroga").
    """

    CAMPOS_AUDITADOS: tuple = ()

    class Meta:
        abstract = True

    @classmethod
    def _campos_auditados(cls):
        if cls.CAMPOS_AUDITADOS:
            return cls.CAMPOS_AUDITADOS
        return tuple(f.attname for f in cls._meta.concrete_fields if f.attname not in ("creado_en", "actualizado_en"))

    def _registrar(self, accion, cambios):
        u = resolver_usuario()
        AuditLog.objects.create(
            usuario=u, usuario_nombre=getattr(u, "username", ""), ip=ip_actual(), accion=accion,
            modelo=self._meta.label, objeto_id=str(self.pk), objeto_repr=str(self)[:200],
            cambios=cambios, motivo=(getattr(self, "motivo_auditoria", "") or "")[:255],
        )

    def save(self, *args, **kwargs):
        campos = self._campos_auditados()
        es_nuevo = self._state.adding
        anterior = {} if es_nuevo else (type(self).objects.filter(pk=self.pk).values(*campos).first() or {})
        super().save(*args, **kwargs)
        if es_nuevo:
            cambios = {c: [None, _valor(getattr(self, c))] for c in campos}
            self._registrar(AuditLog.Accion.CREAR, cambios)
            return
        cambios = {
            c: [_valor(anterior.get(c)), _valor(getattr(self, c))]
            for c in campos if anterior.get(c) != getattr(self, c)
        }
        if cambios:
            self._registrar(AuditLog.Accion.MODIFICAR, cambios)

    def delete(self, *args, **kwargs):
        cambios = {c: [_valor(getattr(self, c)), None] for c in self._campos_auditados()}
        self._registrar(AuditLog.Accion.ELIMINAR, cambios)
        return super().delete(*args, **kwargs)


class Usuario(AuditableModel, AbstractUser):
    """Usuario del CRM con un rol de negocio.

    | Acción                                         | Admin | Tesorero | Cobrador |
    |------------------------------------------------|:-----:|:--------:|:--------:|
    | Consultar clientes, facturas, OC               |   ✔   |    ✔     |    ✔     |
    | Crear/editar clientes, facturas, OC            |   ✔   |    ✔     |          |
    | Anular facturas, cambiar vencimientos          |   ✔   |    ✔     |          |
    | Consultar la bitácora de auditoría             |   ✔   |          |          |
    | Gestionar usuarios y parámetros (Django admin) |   ✔   |          |          |
    """

    class Rol(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        TESORERO = "tesorero", "Tesorero"
        COBRADOR = "cobrador", "Cobrador"

    rol = models.CharField(max_length=15, choices=Rol.choices, default=Rol.COBRADOR)

    # Cambios de rol y de acceso quedan en la auditoría (nunca la contraseña).
    CAMPOS_AUDITADOS = ("username", "rol", "is_active", "is_staff", "is_superuser")

    class Meta:
        db_table = "usuarios"

    @property
    def es_administrador(self) -> bool:
        return self.is_superuser or self.rol == self.Rol.ADMINISTRADOR

    @property
    def es_tesorero(self) -> bool:
        """Tesorero o superior."""
        return self.es_administrador or self.rol == self.Rol.TESORERO

    def save(self, *args, **kwargs):
        # El administrador del CRM necesita entrar al admin de Django.
        if self.rol == self.Rol.ADMINISTRADOR:
            self.is_staff = True
        super().save(*args, **kwargs)
