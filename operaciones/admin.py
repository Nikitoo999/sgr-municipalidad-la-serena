from django import forms
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from sgr_core.admin_base import StandardAdmin
from .models import Task, Activity, Evidence, Employee, TaskReassignment, Benefit
 
 
def _get_employee(request):
    return getattr(request.user, "employee", None)
 
 
def _is_jefatura(request):
    emp = _get_employee(request)
    return emp is not None and emp.role == "jefatura"
 
 
def _is_usuario(request):
    emp = _get_employee(request)
    return emp is not None and emp.role == "usuario"
 
 
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
 
 
class TaskReassignmentInline(admin.TabularInline):
    """Historial de derivaciones visible dentro de la tarea.
 
    Las derivaciones ya registradas se ven de solo lectura (es un historial);
    solo Jefatura/superusuario puede agregar una nueva.
    """
    model = TaskReassignment
    extra = 0
    fields = ('reassigned_at', 'original_employee', 'reassigned_employee', 'reason', 'notes')
    autocomplete_fields = ('original_employee', 'reassigned_employee')
    ordering = ('-reassigned_at',)
    verbose_name_plural = "Historial de derivaciones"
 
    def _allowed(self, request):
        return request.user.is_superuser or _is_jefatura(request)
 
    def has_view_permission(self, request, obj=None):
        return self._allowed(request)
 
    def has_add_permission(self, request, obj=None):
        return self._allowed(request)
 
    def has_change_permission(self, request, obj=None):
        return False
 
    def has_delete_permission(self, request, obj=None):
        return False
 
 
class BenefitInline(admin.TabularInline):
    """Beneficios entregados a un funcionario (se ven dentro del funcionario)."""
    model = Benefit
    extra = 0
    fields = ('benefit_type', 'delivery_area', 'delivered', 'delivered_at')
    show_change_link = True
 
 
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
class EmployeeAdmin(StandardAdmin):
    list_display = ('nombre_completo', 'user', 'rut', 'address', 'delegation', 'role')
    list_filter = ('delegation', 'role')
    # Búsqueda de encargados por RUT, nombre y dirección
    # (varias palabras: cada una debe coincidir con algún campo, ej. "Juan Pérez")
    search_fields = ('rut', 'user__username', 'user__first_name', 'user__last_name', 'address')
    list_select_related = ('user', 'delegation')
    ordering = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [BenefitInline]
 
    @admin.display(description="Nombre", ordering='user__first_name')
    def nombre_completo(self, obj):
        return obj.user.get_full_name() or "—"
 
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if _is_jefatura(request):
            return qs.filter(delegation=request.user.employee.delegation).exclude(user__is_superuser=True)
        return qs.none()
 
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
class TaskAdmin(StandardAdmin):
    form = TaskForm
    list_display = ('title', 'goal', 'due_date', 'status', 'assigned_to')
    list_filter = ('status', 'assigned_to')
    search_fields = ('title',)
    list_select_related = ('goal', 'goal__delegation', 'assigned_to')
    ordering = ('due_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ActivityInline, TaskReassignmentInline]
 
    # Candado de Seguridad (Scoping): Filtra los datos según el usuario logueado
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Si es superadministrador, ve todo
        if request.user.is_superuser:
            return qs
        # Si es un funcionario normal, solo ve las tareas de su delegación
        if hasattr(request.user, 'employee'):
            qs = qs.filter(goal__delegation=request.user.employee.delegation)
            # Usuario ve solo sus tareas asignadas; Jefatura ve todas las de su delegación
            if _is_usuario(request):
                qs = qs.filter(assigned_to=request.user.employee)
            return qs
        # Si no tiene empleado asociado, no ve nada
        return qs.none()
 
 
@admin.register(Activity)
class ActivityAdmin(StandardAdmin):
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
            qs = qs.filter(task__goal__delegation=request.user.employee.delegation)
            if _is_usuario(request):
                qs = qs.filter(task__assigned_to=request.user.employee)
            return qs
        # Si no tiene empleado asociado, no ve nada
        return qs.none()
 
 
@admin.register(Evidence)
class EvidenceAdmin(StandardAdmin):
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
            qs = qs.filter(activity__task__goal__delegation=request.user.employee.delegation)
            if _is_usuario(request):
                qs = qs.filter(activity__task__assigned_to=request.user.employee)
            return qs
        # Si no tiene empleado asociado, no ve nada
        return qs.none()
 
 
@admin.register(TaskReassignment)
class TaskReassignmentAdmin(StandardAdmin):
    list_display = ('task', 'original_employee', 'reassigned_employee', 'reason', 'reassigned_at')
    list_filter = ('reason',)
    search_fields = (
        'task__title',
        'original_employee__rut', 'original_employee__user__first_name', 'original_employee__user__last_name',
        'reassigned_employee__rut', 'reassigned_employee__user__first_name', 'reassigned_employee__user__last_name',
    )
    list_select_related = (
        'task',
        'original_employee', 'original_employee__user', 'original_employee__delegation',
        'reassigned_employee', 'reassigned_employee__user', 'reassigned_employee__delegation',
    )
    date_hierarchy = 'reassigned_at'
    ordering = ('-reassigned_at',)
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('original_employee', 'reassigned_employee')
 
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
 
    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_usuario(request):
            return False
        return super().has_module_permission(request)
 
 
@admin.register(Benefit)
class BenefitAdmin(StandardAdmin):
    list_display = ('employee', 'benefit_type', 'delivery_area', 'delivered_at', 'delivered')
    list_filter = ('benefit_type', 'delivered', 'delivery_area')
    search_fields = (
        'employee__rut', 'employee__user__username',
        'employee__user__first_name', 'employee__user__last_name', 'employee__address',
    )
    list_select_related = ('employee', 'employee__user', 'employee__delegation', 'delivery_area')
    date_hierarchy = 'delivered_at'
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
 
    def has_module_permission(self, request):
        if request.user.is_superuser or _is_jefatura(request):
            return super().has_module_permission(request)
        if _is_usuario(request):
            return False
        return super().has_module_permission(request)