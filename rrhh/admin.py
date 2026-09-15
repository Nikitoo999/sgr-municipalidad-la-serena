from django.contrib import admin
from .models import Rol, Permiso, RolPermiso, Cargo, Delegacion, Funcionario, Auditoria, Notificacion, Comunicacion, Reconocimiento

@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'descripcion')
    search_fields = ('nombre',)

@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'descripcion')
    search_fields = ('nombre',)

@admin.register(RolPermiso)
class RolPermisoAdmin(admin.ModelAdmin):
    list_display = ('id', 'rol', 'permiso')
    list_filter = ('rol',)

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'nivel_jerarquico')
    list_filter = ('nivel_jerarquico',)

@admin.register(Delegacion)
class DelegacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'estado')
    list_filter = ('estado',)
    search_fields = ('nombre',)

@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = ('rut', 'nombre', 'apellidos', 'email', 'rol', 'cargo', 'delegacion', 'estado')
    list_filter = ('delegacion', 'rol', 'cargo', 'estado')
    search_fields = ('rut', 'nombre', 'apellidos', 'email')

@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'funcionario', 'accion', 'entidad_afectada', 'entidad_id')
    list_filter = ('accion', 'entidad_afectada', 'fecha')
    readonly_fields = ('fecha', 'funcionario', 'accion', 'entidad_afectada', 'entidad_id')

@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'funcionario', 'tipo', 'leido', 'fecha')
    list_filter = ('leido', 'tipo')

@admin.register(Comunicacion)
class ComunicacionAdmin(admin.ModelAdmin):
    list_display = ('id', 'remitente', 'destinatario', 'fecha')

@admin.register(Reconocimiento)
class ReconocimientoAdmin(admin.ModelAdmin):
    list_display = ('id', 'funcionario', 'emisor', 'tipo', 'fecha')
    list_filter = ('tipo',)
