from django import forms
from django.contrib import admin
from django.utils import timezone
from .models import Task, Activity, Evidence, Employee, TaskReassignment, Benefit


#Admin Pro: Inlines ----------
class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    fields = ('image_url', 'is_validated', 'created_at')
    readonly_fields = ('created_at',)


class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    fields = ('name', 'execution_date')


#Admin Pro: validación con clean() ----------
class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        goal = cleaned_data.get("goal")
        due_date = cleaned_data.get("due_date")
        if goal and due_date:
            period = goal.period
            if not (period.start_date <= due_date <= period.end_date):
                raise forms.ValidationError(
                    f"El plazo debe estar dentro del período de la meta "
                    f"({period.start_date:%d/%m/%Y} - {period.end_date:%d/%m/%Y})."
                )
        return cleaned_data


#Admin Pro: acción personalizada ----------
@admin.action(description="Validar evidencias seleccionadas")
def validate_evidences(modeladmin, request, queryset):
    # update() no dispara auto_now, por eso se actualiza updated_at a mano
    updated = queryset.filter(is_validated=False).update(
        is_validated=True, updated_at=timezone.now()
    )
    modeladmin.message_user(request, f"{updated} evidencia(s) validada(s).")


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'rut', 'delegation')
    list_filter = ('delegation',)
    search_fields = ('rut', 'user__username', 'user__first_name', 'user__last_name', 'address')
    list_select_related = ('user', 'delegation')
    ordering = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    form = TaskForm
    list_display = ('title', 'goal', 'due_date', 'status')
    list_filter = ('status',)
    search_fields = ('title',)
    list_select_related = ('goal', 'goal__delegation')
    ordering = ('due_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ActivityInline]

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
    list_filter = ('execution_date',)
    search_fields = ('name', 'task__title')
    list_select_related = ('task',)
    ordering = ('-execution_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [EvidenceInline]

    # Candado de Seguridad (Scoping): Filtra los datos según el usuario logueado
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si es superadministrador, ve todo
        if request.user.is_superuser:
            return qs
        # Si es un funcionario normal, solo ve las actividades de su delegación
        if hasattr(request.user, 'employee'):
            return qs.filter(task__goal__delegation=request.user.employee.delegation)
        # Si no tiene empleado asociado, no ve nada
        return qs.none()


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ('activity', 'is_validated', 'created_at')
    list_filter = ('is_validated', 'created_at')
    search_fields = ('activity__name',)
    list_select_related = ('activity',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    actions = [validate_evidences]

    # Candado de Seguridad (Scoping): Filtra los datos según el usuario logueado
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si es superadministrador, ve todo
        if request.user.is_superuser:
            return qs
        # Si es un funcionario normal, solo ve las evidencias de su delegación
        if hasattr(request.user, 'employee'):
            return qs.filter(activity__task__goal__delegation=request.user.employee.delegation)
        # Si no tiene empleado asociado, no ve nada
        return qs.none()


@admin.register(TaskReassignment)
class TaskReassignmentAdmin(admin.ModelAdmin):
    list_display = ('task', 'original_employee', 'reassigned_employee', 'reason', 'reassigned_at')
    list_filter = ('reason',)
    search_fields = ('task__title', 'original_employee__rut', 'reassigned_employee__rut')
    list_select_related = ('task', 'original_employee', 'reassigned_employee')
    ordering = ('-reassigned_at',)
    readonly_fields = ('created_at', 'updated_at')

    # Candado de Seguridad (Scoping): Filtra los datos según el usuario logueado
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si es superadministrador, ve todo
        if request.user.is_superuser:
            return qs
        # Si es un funcionario normal, solo ve las derivaciones de su delegación
        if hasattr(request.user, 'employee'):
            return qs.filter(task__goal__delegation=request.user.employee.delegation)
        # Si no tiene empleado asociado, no ve nada
        return qs.none()


@admin.register(Benefit)
class BenefitAdmin(admin.ModelAdmin):
    list_display = ('employee', 'benefit_type', 'delivery_area', 'delivered_at', 'delivered')
    list_filter = ('benefit_type', 'delivered', 'delivery_area')
    search_fields = ('employee__rut', 'employee__user__username')
    list_select_related = ('employee', 'employee__user', 'delivery_area')
    ordering = ('-delivered_at',)
    readonly_fields = ('created_at', 'updated_at')

    # Candado de Seguridad (Scoping): Filtra los datos según el usuario logueado
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si es superadministrador, ve todo
        if request.user.is_superuser:
            return qs
        # Si es un funcionario normal, solo ve los beneficios de su delegación
        if hasattr(request.user, 'employee'):
            return qs.filter(employee__delegation=request.user.employee.delegation)
        # Si no tiene empleado asociado, no ve nada
        return qs.none()
