from django.contrib import admin
from .models import AtencionSocial, Compromiso, Actividad, Evidencia

@admin.register(AtencionSocial)
class AtencionSocialAdmin(admin.ModelAdmin):
    list_display = ('rut_usuario_atendido', 'nombre_usuario_atendido', 'tipo_gestion', 'resultado', 'fecha_registro')
    search_fields = ('rut_usuario_atendido', 'nombre_usuario_atendido')

@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'estado', 'territorio', 'fecha_limite', 'funcionario', 'meta')
    list_filter = ('estado', 'territorio', 'funcionario__delegacion')
    search_fields = ('titulo', 'solicitante')

@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'estado', 'funcionario', 'item_medicion', 'fecha_limite')
    list_filter = ('estado', 'funcionario__delegacion')
    search_fields = ('nombre', 'descripcion')

@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ('codigo_unico', 'actividad', 'estado_validacion', 'verificador', 'fecha_subida')
    list_filter = ('estado_validacion', 'fecha_subida')
    search_fields = ('codigo_unico', 'actividad__nombre')
