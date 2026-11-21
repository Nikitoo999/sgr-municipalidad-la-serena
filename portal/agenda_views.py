from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone
from operaciones.models import Activity, Employee, Evidence, Task
from sgr_core.models import InstitutionalGoal, ProjectItem


from . import access
from .access import ModulePermissionMixin
from .modules import MODULE_ICONS, MODULE_LABELS
from .audit import audit

def tareas_del_alcance(request):
    """Tareas que el usuario puede ver según su rol y la delegación activa."""
    role = access.get_role(request.user)
    active = access.get_active_delegation(request)
    qs = Task.objects.filter(deleted_at__isnull=True)
    if role is None or active is None:
        return qs.none()
    if active != access.ALL_DELEGATIONS:
        qs = qs.filter(goal__delegation_id=active.pk)
    if role.scope == "own_records":
        qs = qs.filter(assigned_to__user_id=request.user.pk)
    return qs

def items_de_la_tarea(tarea):
    """Ítems de la matriz del cargo del responsable (vacío si no tiene cargo)."""
    empleado = tarea.assigned_to
    if empleado is None or empleado.position_id is None:
        return ProjectItem.objects.none()
    return ProjectItem.objects.filter(
        position_goals__position_id=empleado.position_id, deleted_at__isnull=True,
    ).distinct().order_by("code")

class AgendaView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/agenda.html"
    module = "tasks"
    action = "view"

    def _tareas(self):
        """Tareas visibles según rol, delegación activa y filtro de estado."""
        role = access.get_role(self.request.user)
        active = access.get_active_delegation(self.request)
        qs = Task.objects.filter(deleted_at__isnull=True)
        if role is None or active is None:
            return qs.none()
        if active != access.ALL_DELEGATIONS:
            qs = qs.filter(goal__delegation_id=active.pk)
        if role.scope == "own_records":
            qs = qs.filter(assigned_to__user_id=self.request.user.pk)

        estado = self.request.GET.get("estado", "")
        if estado in dict(Task._meta.get_field("status").choices):
            qs = qs.filter(status=estado)

        actividades = Prefetch(
            "activities",
            queryset=Activity.objects.filter(deleted_at__isnull=True)
            .select_related("item")
            .order_by("execution_date", "pk")
            .prefetch_related(
                Prefetch("evidences", queryset=Evidence.objects.filter(deleted_at__isnull=True))
            ),
        )
        return (
            qs.select_related("goal", "assigned_to__user")
            .prefetch_related(actividades)
            .order_by("due_date", "pk")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)

        tareas = list(self._tareas())
        for tarea in tareas:
            tarea.items_matriz = list(items_de_la_tarea(tarea))
            for actividad in tarea.activities.all():
                evidencias = list(actividad.evidences.all())
                actividad.lista_evidencias = evidencias
                actividad.n_evidencias = len(evidencias)
                actividad.n_validadas = sum(1 for e in evidencias if e.is_validated)

        context.update({
            "active_module": "tasks",
            "module_label": MODULE_LABELS["tasks"],
            "module_icon": MODULE_ICONS["tasks"],
            "tareas": tareas,
            "estado": self.request.GET.get("estado", ""),
            "estados": Task._meta.get_field("status").choices,
            "can_create": info.can("tasks", "create"),
            "can_edit": info.can("tasks", "edit"),
        })
        return context

class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ["name", "execution_date", "item"]


class ActivityCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Registra una actividad dentro de una tarea (solo POST)."""

    module = "tasks"
    action = "create"

    def post(self, request, task_id):
        tarea = get_object_or_404(tareas_del_alcance(request), pk=task_id)
        form = ActivityForm(request.POST)
        form.fields["item"].queryset = items_de_la_tarea(tarea)
        if form.is_valid():
            actividad = form.save(commit=False)
            actividad.task = tarea
            actividad.save()
            messages.success(request, f"Actividad registrada en {tarea.code}.")
        else:
            messages.error(request, "No se pudo registrar la actividad: revisa el nombre y la fecha.")
        return redirect("tasks")

class EvidenceForm(forms.ModelForm):
    class Meta:
        model = Evidence
        fields = ["file"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].required = True


class EvidenceCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Sube una evidencia a una actividad (solo POST, multipart)."""

    module = "tasks"
    action = "create"

    def post(self, request, activity_id):
        actividad = get_object_or_404(
            Activity.objects.select_related("task"),
            pk=activity_id, deleted_at__isnull=True,
            task__in=tareas_del_alcance(request),
        )
        form = EvidenceForm(request.POST, request.FILES)
        if form.is_valid():
            evidencia = form.save(commit=False)
            evidencia.activity = actividad
            evidencia.save()
            actividad.status = Activity.Status.DONE
            actividad.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Evidencia guardada en {actividad.task.code}.")
        else:
            errores = "; ".join(e for lista in form.errors.values() for e in lista)
            messages.error(request, f"No se pudo subir la evidencia: {errores}")
        return redirect("tasks")


class EvidenceValidateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Marca una evidencia como validada por jefatura o delegado (solo POST)."""

    module = "tasks"
    action = "edit"

    def post(self, request, evidence_id):
        evidencia = get_object_or_404(
            Evidence.objects.select_related("activity__task"),
            pk=evidence_id, deleted_at__isnull=True,
            activity__task__in=tareas_del_alcance(request),
        )
        if evidencia.is_validated:
            messages.info(request, "Esa evidencia ya estaba validada.")
            return redirect("tasks")

        evidencia.is_validated = True
        evidencia.validated_by = request.user
        evidencia.validated_at = timezone.now()
        evidencia.save(update_fields=["is_validated", "validated_by", "validated_at", "updated_at"])
        audit(
            request, "edit", module="tasks",
            object_repr=f"Evidencia de {evidencia.activity.task.code}",
            detail=f"Validada por {request.user}",
        )
        messages.success(request, f"Evidencia de {evidencia.activity.task.code} validada.")
        return redirect("tasks")


class KanbanView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Kanban de solo lectura: agrupa tareas por estado (Pendiente / En Progreso / Completada).

    Reusa tareas_del_alcance(request) para el filtrado de acceso/scoping.
    Soporta parámetros GET opcionales:
      - goal: ID de InstitutionalGoal para filtrar por meta institucional.
      - assigned_to: ID numérico de Employee o 'unassigned' para assigned_to__isnull=True.
    """

    template_name = "portal/kanban_tasks.html"
    module = "tasks"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)

        # Filtrar por parámetros GET (siempre sobre el base de tareas_del_alcance)
        goal_id = self.request.GET.get("goal")
        assigned_to = self.request.GET.get("assigned_to")

        # Filtrar por meta institucional (solo si goal es un número entero válido)
        if goal_id and goal_id.isdigit():
            tareas_qs = (
                tareas_del_alcance(self.request)
                .filter(goal_id=goal_id)
                .select_related("goal", "assigned_to__user")
                .prefetch_related(
                    Prefetch(
                        "activities",
                        queryset=Activity.objects.filter(deleted_at__isnull=True)
                        .prefetch_related(
                            Prefetch(
                                "evidences",
                                queryset=Evidence.objects.filter(deleted_at__isnull=True),
                            )
                        ),
                    ),
                )
                .order_by("due_date", "pk")
            )
        else:
            # Sin goal: base sin filtrar por meta
            tareas_qs = (
                tareas_del_alcance(self.request)
                .select_related("goal", "assigned_to__user")
                .prefetch_related(
                    Prefetch(
                        "activities",
                        queryset=Activity.objects.filter(deleted_at__isnull=True)
                        .prefetch_related(
                            Prefetch(
                                "evidences",
                                queryset=Evidence.objects.filter(deleted_at__isnull=True),
                            )
                        ),
                    ),
                )
                .order_by("due_date", "pk")
            )

        # Filtrar por responsable (assigned_to)
        if assigned_to and assigned_to != "unassigned" and assigned_to.isdigit():
            tareas_qs = tareas_qs.filter(assigned_to_id=assigned_to)
        elif assigned_to == "unassigned":
            tareas_qs = tareas_qs.filter(assigned_to__isnull=True)

        columnas = {
            "Pendiente": [],
            "En Progreso": [],
            "Completada": [],
        }

        hoy = timezone.localdate()
        for tarea in tareas_qs:
            estado = tarea.status
            if estado not in columnas:
                columnas[estado] = []

            actividades = list(tarea.activities.all())
            total_actividades = len(actividades)
            evidencias_validadas = sum(
                1
                for act in actividades
                for ev in act.evidences.all()
                if ev.is_validated
            )

            vencida = (
                tarea.due_date < hoy
                and estado not in ("Completada",)
            )

            columnas[estado].append(
                {
                    "tarea": tarea,
                    "vencida": vencida,
                    "total_actividades": total_actividades,
                    "evidencias_validadas": evidencias_validadas,
                }
            )

        # Opciones de filtro acotadas al alcance (metas y responsables de las tareas visibles)
        active = access.get_active_delegation(self.request)
        goals_choices = (
            InstitutionalGoal.objects.filter(deleted_at__isnull=True)
            .filter(tasks__deleted_at__isnull=True)
            .filter(tasks__goal__isnull=False)
            .distinct()
            .order_by("name")
        )
        if active is not None and active != access.ALL_DELEGATIONS:
            goals_choices = goals_choices.filter(delegation_id=active.pk)

        employees_choices = (
            Employee.objects.filter(deleted_at__isnull=True, user__is_active=True)
            .filter(assigned_tasks__deleted_at__isnull=True)
            .distinct()
            .order_by("user__first_name", "user__last_name")
        )
        if active is not None and active != access.ALL_DELEGATIONS:
            employees_choices = employees_choices.filter(delegation_id=active.pk)

        # Validar que los valores activos sean realmente válidos para el contexto
        goal_active = None
        if goal_id and goal_id.isdigit():
            if goals_choices.filter(pk=goal_id).exists():
                goal_active = goal_id

        assigned_to_active = None
        if assigned_to == "unassigned":
            assigned_to_active = "unassigned"
        elif assigned_to and assigned_to.isdigit():
            if employees_choices.filter(pk=assigned_to).exists():
                assigned_to_active = assigned_to

        context.update(
            {
                "active_module": "tasks",
                "module_label": MODULE_LABELS["tasks"],
                "module_icon": MODULE_ICONS["tasks"],
                "columnas": columnas,
                # Contexto para el formulario de filtrado
                "goal_active": goal_active,
                "assigned_to_active": assigned_to_active,
                "goals_choices": goals_choices,
                "employees_choices": employees_choices,
                "can_edit_tasks": info.can("tasks", "edit"),
            }
        )
        return context


class TaskStatusChangeView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Cambia el estado de una tarea mediante POST (solo Kanban).

    Requiere permiso tasks.edit. Respeta tareas_del_alcance(request)
    (deleted_at__isnull=True, scoping por delegación/rol y own_records).
    """

    module = "tasks"
    action = "edit"

    def post(self, request, task_id):
        tarea = get_object_or_404(tareas_del_alcance(request), pk=task_id)

        validos = dict(Task._meta.get_field("status").choices)
        status = request.POST.get("status", "").strip()
        if status not in validos:
            # Estado inválido: no alterar la BD, redirigir limpio.
            return self._redirect_kanban(request)

        tarea.status = status
        tarea.save()

        return self._redirect_kanban(request)

    def _redirect_kanban(self, request):
        """Redirige al Kanban preservando los filtros goal y assigned_to."""
        params = {}
        for key in ("goal", "assigned_to"):
            valor = request.GET.get(key) or request.POST.get(key)
            if valor:
                params[key] = valor
        url = reverse("kanban_tasks")
        if params:
            url = f"{url}?{urlencode(params)}"
        return redirect(url)