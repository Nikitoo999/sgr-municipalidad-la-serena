from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from .models import (
    Task, Activity, Evidence, Employee, TaskReassignment, Benefit,
    EmployeeDayOff, EmployeeFeedback, TubeEntry,
)

from portal.access import AdminScopedMixin



def _get_employee(request):
    return getattr(request.user, "employee", None)


def _is_jefatura(request):
    emp = _get_employee(request)
    if emp is None or emp.role_id is None:
        return False
    return emp.role.scope in ("authorized", "own_delegation")


def _is_funcionario(request):
    emp = _get_employee(request)
    if emp is None or emp.role_id is None:
        return False
    return emp.role.scope == "own_records"


#Admin Pro: Inlines ----------
class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    fields = ('image_url', 'file', 'is_validated', 'created_at')
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
    if not request.user.is_superuser and not _is_jefatura(request):
        modeladmin.message_user(
            request,
            "No tienes permiso para validar evidencias (solo Jefatura o superusuario).",
            level=messages.ERROR,
        )
        return
    # update() no dispara auto_now, por eso se actualiza updated_at a mano
    updated = queryset.filter(is_validated=False).update(
        is_validated=True, updated_at=timezone.now()
    )
    modeladmin.message_user(request, f"{updated} evidencia(s) validada(s).")


@admin.register(Employee)
class EmployeeAdmin(AdminScopedMixin, admin.ModelAdmin):
    list_display = ('user', 'rut', 'delegation', 'role', 'position')
    list_filter = ('delegation', 'role', 'position')
    search_fields = ('rut', 'user__username', 'user__first_name', 'user__last_name', 'address')
    list_select_related = ('user', 'delegation')
    ordering = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_funcionario(request):
            return False
        return super().has_module_permission(request)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and obj.user_id:
            from django.contrib.auth.models import User
            target = obj.user if hasattr(obj, "user") else None
            if target is None:
                target = User.objects.filter(pk=obj.user_id).first()
            if target is not None and target.is_superuser:
                raise PermissionDenied("No puedes modificar un funcionario de superusuario.")
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return super().has_delete_permission(request, obj)
        if obj is not None and getattr(getattr(obj, "user", None), "is_superuser", False):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Task)
class TaskAdmin(AdminScopedMixin, admin.ModelAdmin):
    form = TaskForm
    list_display = ('title', 'goal', 'due_date', 'status', 'assigned_to')
    list_filter = ('status', 'assigned_to')
    search_fields = ('title',)
    list_select_related = ('goal', 'goal__delegation', 'assigned_to')
    ordering = ('due_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ActivityInline]

    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_funcionario(request):
            return False
        return super().has_module_permission(request)


@admin.register(Activity)
class ActivityAdmin(AdminScopedMixin, admin.ModelAdmin):
    list_display = ('name', 'task', 'execution_date')
    list_filter = ('execution_date',)
    search_fields = ('name', 'task__title')
    list_select_related = ('task',)
    ordering = ('-execution_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [EvidenceInline]

    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_funcionario(request):
            return False
        return super().has_module_permission(request)


@admin.register(Evidence)
class EvidenceAdmin(AdminScopedMixin, admin.ModelAdmin):
    list_display = ('activity', 'is_validated', 'created_at')
    list_filter = ('is_validated', 'created_at')
    search_fields = ('activity__name',)
    list_select_related = ('activity',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    actions = [validate_evidences]

    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_funcionario(request):
            return False
        return super().has_module_permission(request)


@admin.register(TaskReassignment)
class TaskReassignmentAdmin(AdminScopedMixin, admin.ModelAdmin):
    list_display = ('task', 'original_employee', 'reassigned_employee', 'reason', 'reassigned_at')
    list_filter = ('reason',)
    search_fields = ('task__title', 'original_employee__rut', 'reassigned_employee__rut')
    list_select_related = ('task', 'original_employee', 'reassigned_employee')
    ordering = ('-reassigned_at',)
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_funcionario(request):
            return False
        return super().has_module_permission(request)


@admin.register(Benefit)
class BenefitAdmin(AdminScopedMixin, admin.ModelAdmin):
    list_display = ('employee', 'benefit_type', 'delivery_area', 'delivered_at', 'delivered')
    list_filter = ('benefit_type', 'delivered', 'delivery_area')
    search_fields = ('employee__rut', 'employee__user__username')
    list_select_related = ('employee', 'employee__user', 'delivery_area')
    ordering = ('-delivered_at',)
    readonly_fields = ('created_at', 'updated_at')

    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_funcionario(request):
            return False
        return super().has_module_permission(request)


@admin.register(EmployeeDayOff)
class EmployeeDayOffAdmin(admin.ModelAdmin):
    list_display = ('employee', 'kind', 'start_date', 'end_date', 'business_days')
    list_filter = ('kind',)
    search_fields = ('employee__user__username', 'employee__user__first_name', 'employee__user__last_name')
    list_select_related = ('employee__user',)
    ordering = ('-start_date',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(EmployeeFeedback)
class EmployeeFeedbackAdmin(admin.ModelAdmin):
    list_display = ('employee', 'kind', 'date', 'description', 'registered_by')
    list_filter = ('kind',)
    search_fields = ('employee__user__username', 'employee__user__first_name', 'employee__user__last_name', 'description')
    list_select_related = ('employee__user', 'registered_by')
    ordering = ('-date',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TubeEntry)
class TubeEntryAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'channel', 'delegation', 'responsible', 'status', 'request_date')
    list_filter = ('channel', 'status', 'delegation', 'origin')
    search_fields = ('title', 'requester', 'letter_number', 'verification_code')
    list_select_related = ('delegation', 'responsible__user')
    ordering = ('-request_date',)
    readonly_fields = ('verification_code', 'created_at', 'updated_at')