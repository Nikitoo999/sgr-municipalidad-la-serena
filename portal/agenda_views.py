from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone



from operaciones.models import Activity, Evidence, Task

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
        fields = ["name", "execution_date"]


class ActivityCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Registra una actividad dentro de una tarea (solo POST)."""

    module = "tasks"
    action = "create"

    def post(self, request, task_id):
        tarea = get_object_or_404(tareas_del_alcance(request), pk=task_id)
        form = ActivityForm(request.POST)
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