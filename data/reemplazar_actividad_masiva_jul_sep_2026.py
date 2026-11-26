"""Reemplazo puntual para la copia local inspeccionada. Sin --apply solo comprueba."""

import argparse
from collections import Counter
from datetime import datetime, time, timedelta
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models.deletion import Collector
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones import rules
from operaciones.management.commands.seed_demo_data import demo_photo
from operaciones.models import Activity, Attention, Employee, Evidence, Neighbor, Task, TubeEntry, TubeStatusChange
from operaciones.tareas_tubos import vincular_tubo
from sgr_core.models import AttentionSubtype, InstitutionalGoal, Period

MARK = "[Demo Jul-Sep 2026] "
EXPECTED = {"Task": 60, "TubeEntry": 60, "Activity": 60, "Evidence": 60, "TubeStatusChange": 12, "Attention": 1800}
TUBE_STATES = tuple(status for status in TubeEntry.Status.values if status != TubeEntry.Status.NOT_APPLICABLE)
OLD_TASK_IDS = tuple(range(9, 69))
OLD_ATTENTION_IDS = tuple(range(16, 1816))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def old_records():
    tasks = Task.objects.filter(pk__in=OLD_TASK_IDS).order_by("pk")
    for number, task in enumerate(tasks, 1):
        require(task.title == f"Tarea masiva #{number:04d}" and
                task.description == f"Tarea creada por seed_demo (volumen masivo #{number:04d}).",
                f"Tarea {task.pk} modificada; se cancela.")
    require(tasks.count() == 60, "El lote original de tareas ya cambió.")
    attentions = Attention.objects.filter(pk__in=OLD_ATTENTION_IDS).order_by("pk")
    for number, attention in enumerate(attentions, 1):
        require(attention.description.startswith(f"Registro masivo de atención #{number:05d} - "),
                f"Atención {attention.pk} modificada; se cancela.")
    require(attentions.count() == 1800, "El lote original de atenciones ya cambió.")
    linked = TubeEntry.objects.filter(source_task__in=tasks)
    require(set(linked.values_list("pk", flat=True)) == set(OLD_TASK_IDS), "Los tubos vinculados cambiaron.")
    for tube in linked.select_related("source_task"):
        require(tube.title == tube.source_task.title and
                tube.notes.startswith(f"Tarea migrada del Kanban (ID {tube.source_task_id})."),
                f"Tubo {tube.pk} modificado; se cancela.")
    require(not Activity.objects.filter(task__in=tasks).exclude(name__regex=r"^Actividad masiva #[0-9]{4}$").exists(),
            "Hay actividades ajenas al lote vinculadas a las tareas.")
    require(not Evidence.objects.filter(activity__task__in=tasks)
            .exclude(image_url__regex=r"^https://ejemplo\.cl/evidencias/masiva-[0-9]{5}\.jpg$").exists(),
            "Hay evidencias ajenas al lote vinculadas a las tareas.")
    collector = Collector(using="default")
    collector.collect(tasks)
    collector.collect(attentions)
    counts = Counter({model.__name__: len(rows) for model, rows in collector.data.items()})
    for queryset in collector.fast_deletes:
        counts[queryset.model.__name__] += queryset.count()
    require(+counts == Counter(EXPECTED) and not collector.field_updates, f"Cascadas inesperadas: {counts}")
    return collector


def backup():
    directory = Path(__file__).resolve().parent
    path = directory / f"antes-actividad-masiva-{timezone.now():%Y%m%d-%H%M%S-%f}.sqlite3"
    connection.ensure_connection()
    destination = sqlite3.connect(path)
    try:
        connection.connection.backup(destination)
        require(destination.execute("PRAGMA integrity_check").fetchone() == ("ok",), "Respaldo inválido.")
        require(destination.execute("SELECT COUNT(*) FROM tarea_agenda WHERE id BETWEEN 9 AND 68").fetchone() == (60,),
                "Respaldo incompleto.")
    finally:
        destination.close()
    print(f"Respaldo verificado: {path}", flush=True)


def historical_time(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def historical_save(record, moment):
    record.full_clean()
    record.save()
    type(record).objects.filter(pk=record.pk).update(created_at=moment, updated_at=moment)
    record.created_at = moment


def seed(period, photos):
    goals = list(InstitutionalGoal.alive.filter(period=period, delegation__status="Activa",
                                               delegation__deleted_at__isnull=True).select_related("delegation").order_by("pk"))
    subtypes = list(AttentionSubtype.alive.filter(status="Activo", attention_type__status="Activo",
                                                 attention_type__deleted_at__isnull=True).select_related("attention_type"))
    neighbors = list(Neighbor.alive.filter(identifier__startswith="NBR-", status="Activo",
                                          employee__isnull=True).exclude(phone="").order_by("pk")[:15])
    employees = {}
    for employee in Employee.alive.filter(user__is_active=True, role__status="Activo").select_related("user", "role").order_by("pk"):
        employees.setdefault(employee.delegation_id, []).append(employee)
    require(goals and subtypes and len(neighbors) == 15 and all(g.delegation_id in employees for g in goals),
            "Faltan metas, responsables, solicitantes o subtipos activos.")

    task_topics = ("Visita de inspección barrial", "Revisión de luminarias", "Catastro de accesibilidad",
                   "Coordinación con junta vecinal", "Inspección de juegos infantiles")
    for index in range(25):
        goal = goals[index % len(goals)]
        staff = employees[goal.delegation_id]
        day = period.start_date + timedelta(days=2 + 3 * index)
        task = Task(
            goal=goal, assigned_to=staff[(index // len(goals)) % len(staff)],
            title=f"{MARK}{task_topics[index % len(task_topics)]} · A{index + 1:02d}",
            status="Pendiente" if index % 2 == 0 else "En Progreso",
            due_date=day + timedelta(days=6), description="Caso de prueba de seguimiento en terreno.",
        )
        historical_save(task, historical_time(day))
        entry, _ = vincular_tubo(task)
        TubeEntry.objects.filter(pk=entry.pk).update(created_at=task.created_at, updated_at=task.created_at)
        entry.history.update(created_at=task.created_at, updated_at=task.created_at)

    statuses = [TubeEntry.Status.RECEIVED] * 15 + [TubeEntry.Status.PENDING] * 2
    statuses += [TubeEntry.Status.IN_PROGRESS] * 3 + [TubeEntry.Status.DONE] * 15
    tube_topics = ("Retiro de ramas", "Lavado de vereda", "Reparación de juegos", "Revisión de señalética",
                   "Despeje de acceso peatonal", "Reposición de luminaria", "Limpieza de microbasural")
    for index, status in enumerate(statuses):
        goal = goals[index % len(goals)]
        staff = employees[goal.delegation_id]
        day = period.start_date + timedelta(days=3 + 2 * index)
        due = day + timedelta(days=7)
        entry = TubeEntry(
            delegation=goal.delegation, responsible=staff[index % len(staff)],
            channel=TubeEntry.Channel.DELEGATION, origin=TubeEntry.Origin.EXTERNAL,
            title=f"{MARK}{tube_topics[index % len(tube_topics)]} · T{index + 1:02d}",
            requester="Junta vecinal de demostración", territory=goal.delegation.name,
            request_date=day, due_date=due, support_area="Operaciones territoriales",
            status=status, notes="Solicitud local de prueba para el trimestre julio a septiembre.",
        )
        if status == TubeEntry.Status.DONE:
            entry.completed_at = historical_time(due, 16)
            entry.proof_image = demo_photo()
            entry.full_clean()
            entry.proof_image.save(entry.proof_image.name, entry.proof_image.file, save=False)
            photos.append(entry.proof_image)
        historical_save(entry, historical_time(day))
        if status == TubeEntry.Status.DONE:
            historical_save(TubeStatusChange(
                entry=entry, kind=TubeStatusChange.Kind.CLOSED, to_value=entry.get_status_display(),
                notes="Cierre de prueba con respaldo simulado.",
            ), entry.completed_at)
            TubeEntry.objects.filter(pk=entry.pk).update(updated_at=entry.completed_at)

    states = (Attention.AttentionStatus.RECEIVED, Attention.AttentionStatus.IN_PROGRESS, Attention.AttentionStatus.RESOLVED)
    for index, neighbor in enumerate(neighbors):
        goal = goals[index % len(goals)]
        staff = employees[goal.delegation_id]
        responsible = staff[(index // len(goals)) % len(staff)]
        subtype = subtypes[index % len(subtypes)]
        eligible_items = rules.items_for_employee(responsible, period)
        item = eligible_items.filter(pk=subtype.item_id).first()
        day = period.start_date + timedelta(days=2 + 5 * index)
        historical_save(Attention(
            neighbor=neighbor, delegation=goal.delegation, responsible=responsible.user,
            attention_type=subtype.attention_type, attention_subtype=subtype, item=item,
            description=f"{MARK}{subtype.name} · C{index + 1:02d}. Seguimiento de solicitud vecinal.",
            status=states[index % len(states)], counts_for_score=rules.attention_counts_for_score(responsible.user, subtype),
        ), historical_time(day))


def verify_views(period):
    from portal.tests.helpers import TEST_STORAGES

    admin = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
    require(admin is not None, "Falta una cuenta de superadministración para verificar las vistas.")
    with override_settings(ALLOWED_HOSTS=["testserver"], STORAGES=TEST_STORAGES, SECURE_SSL_REDIRECT=False):
        client = Client()
        client.force_login(admin)
        client.post(reverse("switch_period"), {"period": period.pk})
        client.post(reverse("switch_delegation"), {"delegation": "ALL"})
        board = client.get(reverse("tubes"))
        require(board.status_code == 200, "Falló la consulta del tablero.")
        states = {
            col["estado"]: sum(entry.title.startswith(MARK) for entry in col["tarjetas"])
            for col in board.context_data["columnas"]
        }
        require(states == dict.fromkeys(TUBE_STATES, 15), f"Distribución en tablero incorrecta: {states}")
        agenda = client.get(reverse("tasks"))
        require(agenda.status_code == 200 and sum(task.title.startswith(MARK) for task in agenda.context_data["tareas"]) == 25,
                "La agenda no refleja las 25 tareas.")
        attentions = client.get(reverse("attentions"), {"limpiar": "1"}, follow=True)
        require(attentions.status_code == 200 and
                attentions.context_data["page_obj"].paginator.object_list.filter(description__startswith=MARK).count() == 15,
                "El listado no refleja las 15 atenciones.")
        home = client.get(reverse("home"))
        require(home.status_code == 200 and home.context_data["ritmo"]["periodo"] == period
                and home.context_data["kpis"]["tubos_activos"] >= 45
                and home.context_data["kpis"]["atenciones"] >= 15, "Los KPI no reflejan el lote.")
    print(f"Vistas verificadas: tablero {states}; agenda 25; atenciones 15; KPI {home.context_data['kpis']}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    expected_path = Path(__file__).resolve().parents[1] / "db.sqlite3"
    require(connection.vendor == "sqlite" and Path(connection.settings_dict["NAME"]).resolve() == expected_path,
            "Este reemplazo solo admite la base SQLite local revisada.")
    period = Period.alive.get(pk=1, name="Trimestre Jul-Sep 2026")
    require(period.start_date.isoformat() == "2026-07-01" and period.end_date.isoformat() == "2026-09-30",
            "El rango del período cambió.")
    require(not Task.objects.filter(title__startswith=MARK).exists()
            and not TubeEntry.objects.filter(title__startswith=MARK).exists()
            and not Attention.objects.filter(description__startswith=MARK).exists(), "El lote nuevo ya existe.")
    old_records()
    print(f"Eliminaciones verificadas: {EXPECTED}. Carga prevista: 60 tubos, 25 tareas y 15 atenciones.", flush=True)
    if not args.apply:
        return
    backup()
    protected = [get_user_model(), Employee, Neighbor, *apps.get_app_config("sgr_core").get_models()]
    photos = []
    try:
        with transaction.atomic():
            before = {model: set(model.objects.values_list("pk", flat=True)) for model in protected}
            _, deleted = old_records().delete()
            require({key.rsplit(".", 1)[-1].lower(): value for key, value in deleted.items()}
                    == {key.lower(): value for key, value in EXPECTED.items()}, f"Borrado inesperado: {deleted}")
            seed(period, photos)
            require(all(ids == set(model.objects.values_list("pk", flat=True)) for model, ids in before.items()),
                    "Cambió un catálogo o un padrón protegido.")
            connection.check_constraints()
            verify_views(period)
    except Exception:
        for photo in photos:
            photo.storage.delete(photo.name)
        raise
    print(f"Confirmado. Eliminados: {deleted}. Creados: 60 tubos, 25 tareas, 15 atenciones.")


if __name__ == "__main__":
    main()
