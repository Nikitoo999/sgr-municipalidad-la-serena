from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from operaciones.models import Task, TubeEntry


class Command(BaseCommand):
    help = (
        "Migra tareas existentes del Kanban al Tubo de Trabajo. "
        "Crea una TubeEntry por cada Task no borrada lógicamente, "
        "manteniendo título, responsable, fechas y estado (mapeado)."
    )

    # Mapeo de estados de Task (kanban) a estados de TubeEntry (tubo).
    # 'Completada' no se marca como 'done' porque eso requiere foto de respaldo
    # y código de verificación (TubeEntry.clean lo impide).
    STATUS_MAP = {
        "Pendiente": TubeEntry.Status.PENDING,
        "En Progreso": TubeEntry.Status.IN_PROGRESS,
        "Completada": TubeEntry.Status.IN_PROGRESS,
    }

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)
        created = 0
        skipped = 0
        errors = 0

        with transaction.atomic():
            for tarea in Task.objects.filter(deleted_at__isnull=True).select_related(
                "goal", "goal__delegation", "assigned_to", "assigned_to__user"
            ):
                # Idempotencia: no volver a crear si ya existe una tubo con esta tarea origen
                nota_buscar = f"Tarea migrada del Kanban (ID {tarea.pk})"
                if TubeEntry.objects.filter(notes__contains=nota_buscar).exists():
                    skipped += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            f"  Saltando tarea {tarea.pk} ({tarea.title}): ya migrada."
                        )
                    continue

                delegacion = tarea.goal.delegation if tarea.goal else None
                if delegacion is None:
                    errors += 1
                    self.stderr.write(
                        f"  ERROR: tarea {tarea.pk} ('{tarea.title}') sin delegación. Saltando."
                    )
                    continue

                responsable = tarea.assigned_to
                requester = (
                    responsable.user.get_full_name() or responsable.user.username
                    if responsable
                    else "Sistema"
                )

                try:
                    tubo = TubeEntry(
                        delegation=delegacion,
                        channel=TubeEntry.Channel.DELEGATION,
                        title=tarea.title,
                        origin=TubeEntry.Origin.INTERNAL,
                        requester=requester,
                        territory="",
                        responsible=responsable,
                        request_date=tarea.created_at.date()
                        if tarea.created_at
                        else timezone.localdate(),
                        due_date=tarea.due_date,
                        support_area="",
                        notes=(
                            f"{nota_buscar}. "
                            f"{tarea.description or ''}"
                        ).strip(),
                        status=self.STATUS_MAP.get(
                            tarea.status, TubeEntry.Status.PENDING
                        ),
                    )
                    tubo.full_clean()
                    tubo.save()
                    created += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            f"  Creado tubo {tubo.code} desde tarea {tarea.pk} "
                            f"('{tarea.title}')."
                        )
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    self.stderr.write(
                        f"  ERROR al migrar tarea {tarea.pk} ('{tarea.title}'): {exc}"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Migración completada: {created} tubo(s) creado(s), "
                f"{skipped} saltado(s) (ya existían), {errors} error(es)."
            )
        )