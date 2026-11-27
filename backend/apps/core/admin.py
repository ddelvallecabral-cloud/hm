from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Rol en el CRM", {"fields": ("rol",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Rol en el CRM", {"fields": ("rol",)}),)
    list_display = ("username", "first_name", "last_name", "rol", "is_active")
    list_filter = ("rol", "is_active")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "usuario_nombre", "accion", "modelo", "objeto_id", "objeto_repr", "motivo")
    list_filter = ("accion", "modelo")
    search_fields = ("objeto_id", "usuario_nombre", "objeto_repr")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
