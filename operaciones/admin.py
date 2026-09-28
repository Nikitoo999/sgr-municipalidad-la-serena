from django import forms
from django.contrib import admin
from .models import Task, Activity, Evidence, Employee

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'rut', 'delegation')
    list_filter = ('delegation',)
    search_fields = ('rut', 'user__username')
    list_select_related = ('user', 'delegation')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'goal', 'due_date', 'status')
    list_filter = ('status',)
    search_fields = ('title',)
    list_select_related = ('goal', 'goal__delegation')

    # Candado de Seguridad (Scoping): Filtra los datos según el usuario logueado
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si es superadministrador, ve todo
        if request.user.is_superuser:
            return qs
        # Si es un funcionario normal, solo ve las tareas de su delegación
        if hasattr(request.user, 'employee'):
            return qs.filter(goal__delegation=request.user.employee.delegation)
        # Si no tiene empleado asociado, no ve nada
        return qs.none()

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('name', 'task', 'execution_date')
    list_select_related = ('task',)

@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('activity', 'is_validated', 'created_at')
    list_filter = ('is_validated',)
    list_select_related = ('activity',)
