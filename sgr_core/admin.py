from django import forms
from django.contrib import admin
from .admin_base import StandardAdmin
from .models import Delegation, Period, InstitutionalGoal, Achievement, MeasurementItem
 
 
# ---------- Inlines (vistas anidadas) ----------
class GoalInline(admin.TabularInline):
    """Metas de un período (se ven dentro del período)."""
    model = InstitutionalGoal
    extra = 0
    fields = ('name', 'delegation', 'weight')
    show_change_link = True
 
 
class MeasurementItemInline(admin.TabularInline):
    """Ítems de medición de una meta (se ven dentro de la meta)."""
    model = MeasurementItem
    extra = 0
    fields = ('name', 'unit_of_measure', 'baseline', 'target_value')
 
 
class AchievementInline(admin.TabularInline):
    """Registros de cumplimiento de una meta."""
    model = Achievement
    extra = 0
    fields = ('percentage', 'updated_at')
    readonly_fields = ('updated_at',)
 
 
# ---------- Admin Pro: validación con clean() ----------
class PeriodForm(forms.ModelForm):
    class Meta:
        model = Period
        fields = "__all__"
 
    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError(
                "La fecha de término no puede ser anterior a la fecha de inicio."
            )
        return cleaned_data
 
 
@admin.register(Delegation)
class DelegationAdmin(StandardAdmin):
    list_display = ('name', 'color', 'created_at', 'updated_at')
    list_editable = ('color',)
    search_fields = ('name',)
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')
 
 
@admin.register(Period)
class PeriodAdmin(StandardAdmin):
    form = PeriodForm
    list_display = ('name', 'quarter', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'quarter')
    search_fields = ('name',)
    ordering = ('-start_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [GoalInline]
 
 
@admin.register(InstitutionalGoal)
class InstitutionalGoalAdmin(StandardAdmin):
    list_display = ('name', 'delegation', 'weight', 'period')
    list_filter = ('period', 'delegation')
    search_fields = ('name',)
    # list_select_related optimiza la BD al traer las FK de una sola vez
    list_select_related = ('delegation', 'period')
    ordering = ('-period__start_date', 'name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MeasurementItemInline, AchievementInline]
 
 
@admin.register(Achievement)
class AchievementAdmin(StandardAdmin):
    list_display = ('goal', 'percentage', 'updated_at')
    list_filter = ('goal__delegation',)
    list_select_related = ('goal',)
    ordering = ('-updated_at',)
    readonly_fields = ('created_at', 'updated_at')
 
 
@admin.register(MeasurementItem)
class MeasurementItemAdmin(StandardAdmin):
    list_display = ('name', 'goal', 'unit_of_measure', 'baseline', 'target_value')
    list_filter = ('goal__delegation',)
    search_fields = ('name',)
    list_select_related = ('goal',)
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')