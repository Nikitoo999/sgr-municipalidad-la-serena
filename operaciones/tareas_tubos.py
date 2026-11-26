"""Proyección de tareas de agenda al Tubo de Trabajo."""

from django.db import transaction
from django.utils import timezone

from .models import Task, TubeEntry, TubeStatusChange


STATUS_MAP = {
    "Pendiente": TubeEntry.Status.PENDING,
    "En Progreso": TubeEntry.Status.IN_PROGRESS,
    # El cierre en tubos exige una foto y el código de verificación.
    "Completada": TubeEntry.Status.IN_PROGRESS,
}


def guardar_tarea_en_tubo(task, user=None):
    """Guarda una tarea nueva y su solicitud como una sola operación."""
    with transaction.atomic():
        task.save()
        vincular_tubo(task, user=user)
    return task


@transaction.atomic
def vincular_tubo(task, user=None, *, buscar_migracion_anterior=False):
    """Crea una única solicitud o vincula la generada por el comando anterior."""
    Task.objects.select_for_update().get(pk=task.pk)
    existing = TubeEntry.objects.filter(source_task=task).first()
    if existing is not None:
        return existing, False
    if buscar_migracion_anterior:
        marker = f"Tarea migrada del Kanban (ID {task.pk})."
        existing = TubeEntry.objects.filter(
            source_task__isnull=True, notes__startswith=marker,
        ).order_by("pk").first()
        if existing is not None:
            existing.source_task = task
            existing.save(update_fields=["source_task"])
            return existing, False

    delegation = task.goal.delegation
    responsible = task.assigned_to
    if responsible is not None and responsible.delegation_id != delegation.pk:
        responsible = None
    entry = TubeEntry(
        source_task=task, delegation=delegation, channel=TubeEntry.Channel.DELEGATION,
        origin=TubeEntry.Origin.INTERNAL, title=task.title, notes=task.description or "",
        responsible=responsible, requester="Agenda municipal",
        request_date=min(timezone.localdate(task.created_at), task.due_date),
        due_date=task.due_date, status=STATUS_MAP.get(task.status, TubeEntry.Status.PENDING),
    )
    entry.full_clean()
    entry.save()
    TubeStatusChange.objects.create(
        entry=entry, kind=TubeStatusChange.Kind.CREATED, changed_by=user,
        to_value=entry.get_status_display(), notes=f"Ingresada desde {task.code}.",
    )
    return entry, True
