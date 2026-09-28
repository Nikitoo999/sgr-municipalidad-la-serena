from django.contrib import admin
from .models import Delegation, Period, InstitutionalGoal, Achievement, MeasurementItem

@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'quarter', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'quarter')

@admin.register(InstitutionalGoal)
class InstitutionalGoalAdmin(admin.ModelAdmin):
    list_display = ('name', 'delegation', 'weight', 'period')
    list_filter = ('period', 'delegation')
    search_fields = ('name',)
    # list_select_related optimiza la BD al traer las FK de una sola vez (Requisito de rúbrica)
    list_select_related = ('delegation', 'period')

@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('goal', 'percentage', 'updated_at')
    list_select_related = ('goal',)

@admin.register(MeasurementItem)
class MeasurementItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'goal', 'baseline', 'target_value')
    list_select_related = ('goal',)
