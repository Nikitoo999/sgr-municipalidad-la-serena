from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.db import IntegrityError

from operaciones.models import Task
from operaciones.tareas_tubos import vincular_tubo


class Command(BaseCommand):
    help = "Crea o vincula la solicitud de tubo de cada tarea de agenda existente."

    def handle(self, *args, **options):
        created = skipped = errors = 0
        tasks = Task.alive.select_related("goal__delegation", "assigned_to").order_by("pk")
        for task in tasks.iterator():
            try:
                tube, was_created = vincular_tubo(task, buscar_migracion_anterior=True)
            except (ValidationError, IntegrityError) as exc:
                errors += 1
                self.stderr.write(f"Error al vincular {task.code}: {exc}")
                continue

            if was_created:
                created += 1
            else:
                skipped += 1
            if options["verbosity"] >= 2:
                self.stdout.write(f"{task.code}: vinculo con {tube.code}.")

        summary = f"Tubos creados: {created}. Vinculos existentes: {skipped}. Errores: {errors}."
        self.stdout.write(self.style.WARNING(summary) if errors else self.style.SUCCESS(summary))
