"""Carga reversible de solicitudes y tareas para probar períodos y alertas."""

from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from operaciones.calculos import periodo_vigente
from operaciones.models import Employee, Task, TubeEntry
from operaciones.periodos import periodo_anterior
from sgr_core.models import Delegation, InstitutionalGoal, Period

MARKER = "[seed_demo_data] "
PHOTO_PREFIX = "seed-demo-data-"

# El orden deja un compromiso y una tarea vencidos incluso en cargas pequeñas.
SCENARIOS = (
    (TubeEntry.Status.PENDING, "Retiro de ramas en la plaza", "Aseo y ornato"),
    ("Pendiente", "Coordinar visita de inspección barrial", ""),
    (TubeEntry.Status.RECEIVED, "Revisión de luminaria en pasaje", "Alumbrado público"),
    ("En Progreso", "Actualizar diagnóstico de accesibilidad", ""),
    (TubeEntry.Status.IN_PROGRESS, "Reparación de juegos infantiles", "Mantención"),
    (TubeEntry.Status.DONE, "Limpieza de microbasural", "Aseo y ornato"),
    ("Completada", "Entregar acta de reunión vecinal", ""),
)


def demo_photo():
    buffer = BytesIO()
    image = Image.new("RGB", (480, 270), "#e2e8e6")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 464, 254), outline="#34554b", width=3)
    draw.text((35, 110), "Respaldo simulado - datos de demostracion", fill="#183c32")
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(f"{PHOTO_PREFIX}{uuid4().hex}.png", buffer.getvalue(), "image/png")


class Command(BaseCommand):
    help = "Crea 20 solicitudes y tareas de demostración o elimina las cargadas por este comando."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=20, help="Número total de tubos y tareas.")
        parser.add_argument("--clean", action="store_true", help="Elimina todas las cargas del comando y sus respaldos.")
        parser.add_argument(
            "--period", choices=("both", "current", "previous"), default="both",
            help="Carga en ambos períodos, solo en el de referencia o solo en el anterior.",
        )
        parser.add_argument("--delegation", metavar="CODIGO", help="Limita la carga a una delegación activa.")

    def handle(self, *args, **options):
        if options["clean"]:
            self.clean()
            return
        count = options["count"]
        if count < 1:
            raise CommandError("--count debe ser mayor que cero.")

        today = timezone.localdate()
        periods = self.get_periods(today, options["period"])
        delegations = Delegation.alive.filter(status="Activa").order_by("code")
        if options["delegation"]:
            delegations = delegations.filter(code__iexact=options["delegation"])
        delegations = list(delegations)
        if not delegations:
            raise CommandError("La carga requiere al menos una delegación activa existente.")

        employees = {}
        for employee in Employee.alive.filter(delegation__in=delegations, user__is_active=True).order_by("pk"):
            employees.setdefault(employee.delegation_id, employee)

        totals = dict.fromkeys((period.pk for period in periods), 0)
        goals = {}
        photos = []
        try:
            with transaction.atomic():
                for index in range(count):
                    slot = index // len(periods)
                    period = periods[index % len(periods)]
                    delegation = delegations[slot % len(delegations)]
                    status, title, area = SCENARIOS[slot % len(SCENARIOS)]
                    start = max(period.start_date, min(period.end_date, today) - timedelta(days=9 + slot % 7))
                    due = min(period.end_date, start + timedelta(days=5))
                    if status == TubeEntry.Status.RECEIVED and period.end_date >= today:
                        due = min(period.end_date, today + timedelta(days=2))
                    responsible = employees.get(delegation.pk)
                    if area:
                        self.create_tube(delegation, status, title, area, start, due, responsible, photos)
                    else:
                        key = (period.pk, delegation.pk)
                        if key not in goals:
                            goals[key] = InstitutionalGoal.alive.filter(
                                period=period, delegation=delegation,
                            ).order_by("pk").first()
                            if goals[key] is None:
                                goals[key] = InstitutionalGoal(
                                    name=f"{MARKER}Gestión territorial", period=period, delegation=delegation,
                                )
                                goals[key].full_clean()
                                goals[key].save()
                        task = Task(
                            goal=goals[key], title=f"{MARKER}{title}", due_date=due,
                            status=status, assigned_to=responsible,
                            description="Caso simulado de seguimiento territorial.",
                        )
                        task.full_clean()
                        task.save()
                    totals[period.pk] += 1
        except Exception:
            for photo in photos:
                photo.storage.delete(photo.name)
            raise

        self.stdout.write(self.style.SUCCESS(f"Se crearon {count} tubos y tareas en total."))
        for period in periods:
            self.stdout.write(f"  {period.name}: {totals[period.pk]}")

    def get_periods(self, today, selection):
        reference = periodo_vigente(today)
        if reference is None or reference.start_date > today:
            reference = Period.alive.filter(start_date__lte=today).order_by("-start_date", "-pk").first()
        if reference is None:
            raise CommandError("La carga requiere un período existente que ya haya comenzado.")
        if selection == "current":
            return [reference]
        previous = periodo_anterior(reference)
        if selection == "previous":
            if previous is None:
                raise CommandError(f"No hay un período anterior a «{reference.name}».")
            return [previous]
        if previous is None:
            self.stdout.write(self.style.WARNING(f"No hay un período anterior a «{reference.name}»."))
            return [reference]
        return [reference, previous]

    def create_tube(self, delegation, status, title, area, start, due, responsible, photos):
        entry = TubeEntry(
            delegation=delegation, title=f"{MARKER}{title}", requester="Junta vecinal de demostración",
            territory=delegation.name, support_area=area, request_date=start, due_date=due, status=status,
            responsible=responsible, notes="Solicitud simulada para probar el seguimiento municipal.",
        )
        if status == TubeEntry.Status.DONE:
            entry.completed_at = timezone.make_aware(datetime.combine(due, time.min))
            entry.proof_image = demo_photo()
        entry.full_clean()
        if entry.proof_image:
            entry.proof_image.save(entry.proof_image.name, entry.proof_image.file, save=False)
            photos.append(entry.proof_image)
        entry.save()

    def clean(self):
        with transaction.atomic():
            tubes = TubeEntry.objects.filter(title__startswith=MARKER)
            tasks = Task.objects.filter(title__startswith=MARKER)
            tube_count, task_count = tubes.count(), tasks.count()
            paths = set(tubes.values_list("proof_image", flat=True))
            tubes.delete()
            tasks.delete()
            InstitutionalGoal.objects.filter(
                name=f"{MARKER}Gestión territorial", tasks__isnull=True, achievements__isnull=True,
            ).delete()
            photos = (
                path for path in paths
                if path and PurePosixPath(path).name.startswith(PHOTO_PREFIX)
            )
            storage = TubeEntry._meta.get_field("proof_image").storage
            for path in photos:
                if not TubeEntry.objects.filter(proof_image=path).exists():
                    transaction.on_commit(lambda path=path: storage.delete(path))
        self.stdout.write(self.style.SUCCESS(f"Se eliminaron {tube_count} tubos y {task_count} tareas de demostración."))
