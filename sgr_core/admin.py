from django.contrib import admin
from .models import Periodo, MetaInstitucional, Cumplimiento, ItemMedicion

@admin.register(Periodo)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'trimestre', 'fecha_inicio', 'fecha_fin', 'dias_computables', 'estado')
    list_filter = ('estado', 'trimestre')

@admin.register(MetaInstitucional)
class MetaInstitucionalAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'delegacion', 'periodo', 'ponderacion')
    list_filter = ('delegacion', 'periodo')
    search_fields = ('nombre',)
    list_select_related = ('delegacion', 'periodo')

@admin.register(Cumplimiento)
class CumplimientoAdmin(admin.ModelAdmin):
    list_display = ('meta', 'porcentaje', 'fecha_calculo')
    list_filter = ('meta__delegacion', 'fecha_calculo')
    list_select_related = ('meta',)

@admin.register(ItemMedicion)
class ItemMedicionAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'meta', 'unidad_medida', 'linea_base', 'valor_objetivo')
    list_filter = ('meta__delegacion', 'tipo')
    search_fields = ('nombre',)
    list_select_related = ('meta',)
