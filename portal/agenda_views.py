from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone
from operaciones.models import Activity, Employee, Evidence, Task
from sgr_core.models import Delegation, InstitutionalGoal, ProjectItem


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
        puede_reasignar = info.can("tasks", "edit")
        candidatos = {}
        for tarea in tareas:
            tarea.items_matriz = list(items_de_la_tarea(tarea))
            tarea.reasignaciones = list(
                tarea.reassignments.select_related("original_employee__user", "reassigned_employee__user")
                .order_by("-reassigned_at")[:3]
            )
            if puede_reasignar:
                deleg_id = tarea.goal.delegation_id
                if deleg_id not in candidatos:
                    candidatos[deleg_id] = list(
                        Employee.objects.filter(
                            deleted_at__isnull=True, user__is_active=True, delegation_id=deleg_id,
                        ).select_related("user").order_by("user__first_name", "user__last_name")
                    )
                tarea.candidatos = [e for e in candidatos[deleg_id] if e.pk != tarea.assigned_to_id]
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
    """Actividad de la agenda (RF-009/RF-010).

    - Nombre y teléfono del usuario: opcionales, pero sin ellos la actividad no
      suma si el ítem es de cara al usuario (punto 2 del nuevo requerimiento).
    - La fecha no puede ser de una semana ya cerrada por plazo (punto 4) ni de
      un período cerrado (RN-013).
    """

    class Meta:
        model = Activity
        fields = ["name", "execution_date", "item", "contact_name", "contact_phone"]

    def clean_contact_phone(self):
        from portal.validators import normalize_phone

        phone = (self.cleaned_data.get("contact_phone") or "").strip()
        if not phone:
            return ""
        try:
            return normalize_phone(phone)
        except forms.ValidationError:
            raise
        except Exception:
            raise forms.ValidationError("Ingresa un teléfono válido, por ejemplo +56 9 1234 5678.")

    def clean_execution_date(self):
        from operaciones import rules
        from sgr_core.models import Period

        fecha = self.cleaned_data.get("execution_date")
        if fecha is None:
            return fecha
        error = rules.past_week_entry_error(fecha)
        if error:
            raise forms.ValidationError(error)
        cerrado = Period.objects.filter(
            deleted_at__isnull=True, status="Cerrado",
            start_date__lte=fecha, end_date__gte=fecha,
        ).first()
        if cerrado is not None:
            raise forms.ValidationError(
                f"La fecha pertenece al período cerrado «{cerrado.name}»: no se puede registrar."
            )
        return fecha


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
            aviso = ""
            if actividad.item_id and actividad.item.requires_contact and not actividad.has_contact:
                aviso = " Sin nombre y teléfono del usuario no sumará puntaje: agrégalos si corresponde."
            messages.success(request, f"Actividad registrada en {tarea.code}.{aviso}")
        else:
            errores = "; ".join(e for lista in form.errors.values() for e in lista)
            messages.error(request, f"No se pudo registrar la actividad: {errores}")
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
    """Revisa una evidencia: aprobar, rechazar o pedir corrección (solo POST).

    RF-013 / CA-02: la decisión registra verificador, fecha, resultado y
    observación (obligatoria al rechazar o pedir corrección). Solo una
    evidencia aprobada hace que la actividad sume. Sin ``decision`` se aprueba
    (compatibilidad con el botón "Validar" anterior). Nadie revisa la
    evidencia de una tarea asignada a sí mismo (segregación de funciones).
    """

    module = "tasks"
    action = "edit"

    def post(self, request, evidence_id):
        from operaciones.models import ReviewStatus

        evidencia = get_object_or_404(
            Evidence.objects.select_related("activity__task__assigned_to"),
            pk=evidence_id, deleted_at__isnull=True,
            activity__task__in=tareas_del_alcance(request),
        )
        codigo = evidencia.activity.task.code
        if evidencia.is_validated:
            messages.info(request, "Esa evidencia ya estaba validada.")
            return redirect("tasks")
        asignado = evidencia.activity.task.assigned_to
        if asignado is not None and asignado.user_id == request.user.pk:
            messages.error(request, "No puedes revisar la evidencia de una tarea asignada a ti.")
            return redirect("tasks")

        decision = request.POST.get("decision") or ReviewStatus.APPROVED
        notes = " ".join((request.POST.get("notes") or "").split())[:500]
        if decision not in (ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.CORRECTION):
            messages.error(request, "Decisión de revisión no válida.")
            return redirect("tasks")
        if decision != ReviewStatus.APPROVED and len(notes) < 5:
            messages.error(request, "Indica la observación para el funcionario (al menos 5 caracteres).")
            return redirect("tasks")

        evidencia.review_status = decision
        evidencia.review_notes = notes
        evidencia.is_validated = decision == ReviewStatus.APPROVED
        evidencia.validated_by = request.user
        evidencia.validated_at = timezone.now()
        evidencia.save(update_fields=[
            "is_validated", "validated_by", "validated_at", "review_status", "review_notes", "updated_at",
        ])
        etiqueta = evidencia.get_review_status_display()
        audit(
            request, "validate", module="tasks",
            object_repr=f"Evidencia de {codigo}",
            detail=f"{etiqueta} por {request.user}" + (f" · {notes}" if notes else ""),
        )
        if evidencia.is_validated:
            messages.success(request, f"Evidencia de {codigo} validada.")
        else:
            messages.success(request, f"Evidencia de {codigo}: {etiqueta.lower()}. El funcionario verá tu observación.")
        return redirect("tasks")


class KanbanView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Kanban de solo lectura: agrupa tareas por estado (Pendiente / En Progreso / Completada).

    Reusa tareas_del_alcance(request) para el filtrado de acceso/scoping.
    Soporta parámetros GET opcionales:
      - goal: ID de InstitutionalGoal para filtrar por meta institucional.
      - assigned_to: ID numérico de Employee o 'unassigned' para assigned_to__isnull=True.
    """

    template_name = "portal/kanban.html"
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

        view_mode = self.request.GET.get("view", "kanban")
        if view_mode not in ("kanban", "tabla"):
            view_mode = "kanban"
        total_tareas = sum(len(items) for items in columnas.values())

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
                "view_mode": view_mode,
                "total_tareas": total_tareas,
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
        for key in ("goal", "assigned_to", "view"):
            valor = request.GET.get(key) or request.POST.get(key)
            if valor:
                params[key] = valor
        url = reverse("kanban_tasks")
        if params:
            url = f"{url}?{urlencode(params)}"
        return redirect(url)


class OrganigramView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Vista de solo lectura del organigrama de empleados por delegación y cargo.

    Requiere permiso users.view. Agrupa empleados por delegación activa y posición.
    """

    module = "users"
    action = "view"
    template_name = "portal/organigrama.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)
        active = access.get_active_delegation(self.request)
        role = info.role

        # Base de empleados visibles (sin borrados lógicos y con cuenta activa)
        qs = Employee.objects.filter(
            deleted_at__isnull=True, user__is_active=True
        ).select_related("user", "delegation", "position", "role")

        # Scoping por delegación activa
        if active is not None and active != access.ALL_DELEGATIONS:
            qs = qs.filter(delegation_id=active.pk)

        # Scoping por rol own_records: solo el propio empleado
        if role is not None and role.scope == "own_records":
            qs = qs.filter(user_id=self.request.user.pk)

        # Filtro GET opcional 'delegation' (solo cuando la delegación activa es ALL)
        delegation_filter = self.request.GET.get("delegation")
        if delegation_filter and active == access.ALL_DELEGATIONS:
            try:
                delegation_filter_int = int(delegation_filter)
                qs = qs.filter(delegation_id=delegation_filter_int)
            except (ValueError, TypeError):
                pass

        # Agrupación: delegación -> cargo -> funcionarios (el cargo CAR01,
        # Delegado, queda primero por el orden de código).
        #
        # Se usan dict normales, NO defaultdict: en la plantilla,
        # ``posiciones.items`` primero intenta ``posiciones["items"]`` y un
        # defaultdict "responde" creando una lista vacía, así que el
        # organigrama se dibujaba sin funcionarios.
        organigrama = {}
        for emp in qs.order_by(
            "delegation__code",
            "position__code",
            "user__first_name",
            "user__last_name",
        ):
            de_key = (
                f"{emp.delegation.code} · {emp.delegation.name}"
                if emp.delegation else "Sin delegación"
            )
            pos_key = emp.position.name if emp.position else "Sin cargo asignado"
            organigrama.setdefault(de_key, {}).setdefault(pos_key, []).append(
                {
                    "employee": emp,
                    "full_name": emp.user.get_full_name() or emp.user.username,
                    "rank": emp.role.rank if emp.role else 0,
                    "scope": emp.role.scope if emp.role else "—",
                    "role_name": emp.role.name if emp.role else "Sin rol",
                }
            )

        context.update(
            {
                "active_module": "users",
                "module_label": MODULE_LABELS["users"],
                "module_icon": MODULE_ICONS["users"],
                "organigrama": organigrama,
                "all_delegations": Delegation.objects.filter(
                    status="Activa", deleted_at__isnull=True
                ).order_by("code"),
                "sgr_can_view_users": info.can("users", "view"),
            }
        )
        return context


class PendingTransferView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Previsualización en solo lectura de tareas pendientes a traspasar trimestralmente.

    Requiere permiso tasks.view. Muestra tareas con status Pendiente o En Progreso
    cuya meta pertenece a un período Cerrado, dentro del alcance del usuario.
    No ejecuta mutaciones ni formularios POST.
    """

    module = "tasks"
    action = "view"
    template_name = "portal/pending_transfer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)

        # Parte de tareas_del_alcance (respeta deleted_at__isnull=True y scoping por
        # delegación activa y rol/own_records)
        qs = tareas_del_alcance(self.request)

        # Solo tareas no completadas, con meta y período válidos y período cerrado
        qs = (
            qs.filter(status__in=["Pendiente", "En Progreso"])
            .filter(goal__deleted_at__isnull=True)
            .filter(goal__period__deleted_at__isnull=True)
            .filter(goal__period__status="Cerrado")
            .select_related(
                "goal",
                "goal__period",
                "goal__delegation",
                "assigned_to",
                "assigned_to__user",
            )
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
                )
            )
            .order_by("goal__delegation__code", "goal__name", "due_date", "pk")
        )

        total_pendientes = qs.count()
        pendientes_count = qs.filter(status="Pendiente").count()
        en_progreso_count = qs.filter(status="En Progreso").count()

        context.update(
            {
                "active_module": "tasks",
                "module_label": MODULE_LABELS["tasks"],
                "module_icon": MODULE_ICONS["tasks"],
                "pending_tasks": qs,
                "total_pendientes": total_pendientes,
                "pendientes_count": pendientes_count,
                "en_progreso_count": en_progreso_count,
                "sgr_can_view_tasks": info.can("tasks", "view"),
                "sgr_can_edit_tasks": info.can("tasks", "edit"),
                "destination_goals": InstitutionalGoal.objects.filter(
                    deleted_at__isnull=True,
                    period__deleted_at__isnull=True,
                    period__status="En curso",
                ).order_by("delegation__code", "name"),
            }
        )
        return context


class PendingTransferExecuteView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Ejecuta el traspaso de una tarea pendiente a una nueva meta institucional.

    Requiere permiso tasks.edit. Clona la tarea origen en la meta destino
    dentro de un período "En curso", sin alterar la tarea origen.
    """

    module = "tasks"
    action = "edit"

    def post(self, request, task_id):
        tarea = get_object_or_404(tareas_del_alcance(request), pk=task_id)

        # Validar estado origen
        if tarea.status not in ("Pendiente", "En Progreso"):
            messages.error(
                request, f"La tarea '{tarea.title}' no está en estado traspasable."
            )
            return redirect("pending_transfer")

        # Validar que la meta origen pertenece a un período cerrado
        if (
            not tarea.goal
            or tarea.goal.deleted_at is not None
            or tarea.goal.period.deleted_at is not None
            or tarea.goal.period.status != "Cerrado"
        ):
            messages.error(
                request,
                "La tarea origen debe pertenecer a una meta de un período cerrado.",
            )
            return redirect("pending_transfer")

        # Leer y validar meta destino
        goal_id = request.POST.get("goal_id", "").strip()
        if not goal_id or not goal_id.isdigit():
            messages.error(request, "Debe seleccionar una meta destino válida.")
            return redirect("pending_transfer")

        try:
            target_goal = InstitutionalGoal.objects.get(
                pk=int(goal_id),
                deleted_at__isnull=True,
                period__deleted_at__isnull=True,
                period__status="En curso",
            )
        except InstitutionalGoal.DoesNotExist:
            messages.error(
                request,
                "La meta destino no existe, no está activa o no pertenece a un período en curso.",
            )
            return redirect("pending_transfer")

        # Validar que la meta destino sea de la misma delegación de la meta origen
        if target_goal.delegation_id != tarea.goal.delegation_id:
            messages.error(
                request,
                "La meta destino debe pertenecer a la misma delegación de la tarea origen.",
            )
            return redirect("pending_transfer")

        # Validar alcance de delegación del usuario
        active = access.get_active_delegation(request)
        if active is not None and active != access.ALL_DELEGATIONS:
            if target_goal.delegation_id != active.pk:
                messages.error(
                    request,
                    "No tiene alcance sobre la delegación de la meta destino.",
                )
                return redirect("pending_transfer")

        # Prevenir duplicados: misma title en la misma meta destino
        if Task.objects.filter(
            goal=target_goal,
            title=tarea.title,
            deleted_at__isnull=True,
        ).exists():
            messages.warning(
                request,
                f"Ya existe una tarea '{tarea.title}' en la meta '{target_goal.name}'. No se creó duplicado.",
            )
            return redirect("pending_transfer")

        # Calcular due_date
        today = timezone.localdate()
        period_end = target_goal.period.end_date
        period_start = target_goal.period.start_date
        if tarea.due_date and period_start <= tarea.due_date <= period_end:
            new_due_date = tarea.due_date
        else:
            new_due_date = period_end

        # Ejecutar clonación atómicamente
        try:
            with transaction.atomic():
                nueva = Task.objects.create(
                    goal=target_goal,
                    title=tarea.title,
                    description=tarea.description,
                    due_date=new_due_date,
                    status="Pendiente",
                    assigned_to=tarea.assigned_to,
                )
        except Exception:
            messages.error(
                request, "Ocurrió un error al crear la tarea. Intente nuevamente."
            )
            return redirect("pending_transfer")

        messages.success(
            request,
            f"Tarea '{nueva.title}' traspasada a la meta '{target_goal.name}' (código {nueva.code}).",
        )
        return redirect("pending_transfer")


class TaskReassignView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Reasigna una tarea a otro funcionario de la delegación (HU-15).

    Conserva responsable anterior, nuevo responsable, autor (auditoría), fecha
    y motivo en ``TaskReassignment``. Solo POST; requiere ``tasks.edit``.
    """

    module = "tasks"
    action = "edit"

    def post(self, request, task_id):
        from operaciones.models import TaskReassignment

        tarea = get_object_or_404(
            tareas_del_alcance(request).select_related("goal", "assigned_to__user"), pk=task_id,
        )
        motivo = request.POST.get("reason", "")
        notas = " ".join((request.POST.get("notes") or "").split())[:500]
        pk = request.POST.get("employee", "")
        nuevo = None
        if pk.isdigit():
            nuevo = Employee.objects.filter(
                pk=int(pk), deleted_at__isnull=True, user__is_active=True,
                delegation_id=tarea.goal.delegation_id,
            ).select_related("user").first()
        motivos = dict(TaskReassignment._meta.get_field("reason").choices)
        if nuevo is None:
            messages.error(request, "Elige un funcionario activo de la delegación de la tarea.")
        elif nuevo.pk == tarea.assigned_to_id:
            messages.info(request, f"{nuevo.full_name} ya es el responsable de {tarea.code}.")
        elif motivo not in motivos:
            messages.error(request, "Indica el motivo de la reasignación.")
        else:
            anterior = tarea.assigned_to
            with transaction.atomic():
                if anterior is not None:
                    TaskReassignment.objects.create(
                        task=tarea, original_employee=anterior, reassigned_employee=nuevo,
                        reason=motivo, reassigned_at=timezone.now(), notes=notas or None,
                    )
                tarea.assigned_to = nuevo
                tarea.save(update_fields=["assigned_to", "updated_at"])
            audit(
                request, "edit", module="tasks", object_repr=f"Tarea {tarea.code}",
                detail=(f"Reasignada {anterior.full_name if anterior else 'sin responsable'} → "
                        f"{nuevo.full_name} ({motivos[motivo]}){': ' + notas if notas else ''}"),
            )
            messages.success(request, f"{tarea.code} reasignada a {nuevo.full_name}.")
        return redirect("tasks")
