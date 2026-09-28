from django import forms
from django.contrib import admin
from .models import AtencionSocial, Compromiso, Actividad, Evidencia



class EvidenciaInline(admin.TabularInline):
    model = Evidencia
    extra = 0
    fields = ('codigo_unico', 'verificador', 'estado_validacion', 'motivo_rechazo', 'fecha_subida')
    readonly_fields = ('fecha_subida',)


@admin.register(AtencionSocial)
class AtencionSocialAdmin(admin.ModelAdmin):
    list_display = ('rut_usuario_atendido', 'nombre_usuario_atendido', 'tipo_gestion', 'resultado', 'fecha_registro')
    search_fields = ('rut_usuario_atendido', 'nombre_usuario_atendido')
    ordering = ('-fecha_registro',)


@admin.register(Compromiso)
class CompromisoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'estado', 'territorio', 'fecha_limite', 'funcionario', 'meta')
    list_filter = ('estado', 'territorio', 'funcionario__delegacion')
    search_fields = ('titulo', 'solicitante')
    list_select_related = ('funcionario', 'meta')
    ordering = ('-fecha_limite',)


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'estado', 'funcionario', 'item_medicion', 'fecha_limite')
    list_filter = ('estado', 'funcionario__delegacion')
    search_fields = ('nombre', 'descripcion')
    list_select_related = ('funcionario', 'item_medicion')
    ordering = ('-fecha_limite','nombre')
    inlines = [EvidenciaInline]   # ← Admin Pro: Inline


# validación con clean() 
class EvidenciaForm(forms.ModelForm):
    class Meta:
        model = Evidencia
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        estado = cleaned_data.get("estado_validacion")
        motivo = cleaned_data.get("motivo_rechazo")
        if estado in ("Rechazada", "Observada") and not motivo:
            raise forms.ValidationError(
                "Debe indicar el motivo de rechazo u observación para este estado."
            )
        return cleaned_data


#Admin Pro: acción personalizada 
@admin.action(description="Aprobar evidencias seleccionadas")
def aprobar_evidencias(modeladmin, request, queryset):
    actualizadas = queryset.exclude(estado_validacion="Aprobada").update(estado_validacion="Aprobada")
    modeladmin.message_user(request, f"{actualizadas} evidencia(s) aprobada(s).")


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    form = EvidenciaForm
    list_display = ('codigo_unico', 'actividad', 'estado_validacion', 'verificador', 'fecha_subida')
    list_filter = ('estado_validacion', 'fecha_subida')
    search_fields = ('codigo_unico', 'actividad__nombre')
    list_select_related = ('actividad', 'verificador')
    ordering = ('-fecha_subida',)
    actions = [aprobar_evidencias]