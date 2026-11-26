"""Reemplazo del lote de demostracion. Sin --apply solo comprueba."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, time, timedelta
import os
import re
import shutil
import subprocess
import tempfile
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
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Q
from django.db.models.deletion import Collector
from django.utils import timezone

from operaciones import rules
from operaciones.management.commands.seed_demo_data import demo_photo
from operaciones.models import Activity, Attention, Employee, Evidence, Neighbor, Task, TubeEntry, TubeStatusChange
from operaciones.periodos import tubos_originados_en
from operaciones.tareas_tubos import vincular_tubo
from sgr_core.models import AttentionSubtype, InstitutionalGoal, Period

MARK = "[Demo Jul-Sep 2026] "
TUBE_STATES = tuple(status for status in TubeEntry.Status.values if status != TubeEntry.Status.NOT_APPLICABLE)
PERIOD_NAME = "Trimestre Jul-Sep 2026"
TASK_TITLE = re.compile(r"Tarea masiva #([0-9]{4})")
ATTENTION_DESCRIPTION = re.compile(r"Registro masivo de atención #([0-9]{5}) - .+\.")
LEGACY_NOTE = re.compile(r"Tarea migrada del Kanban \(ID ([0-9]+)\)(?:\.|$)")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def old_records():
    tasks = {}
    for task in Task.objects.filter(title__startswith="Tarea masiva #"):
        match = TASK_TITLE.fullmatch(task.title)
        if match and 1 <= int(match[1]) <= 60 and task.description == (
            f"Tarea creada por seed_demo (volumen masivo #{match[1]})."
        ):
            tasks[task.pk] = task.title
    task_qs = Task.objects.filter(pk__in=tasks)

    attention_ids = []
    for attention in Attention.objects.filter(description__startswith="Registro masivo de atención #").select_related("neighbor"):
        match = ATTENTION_DESCRIPTION.fullmatch(attention.description)
        if match and 1 <= int(match[1]) <= 1800:
            expected_neighbor = f"NBR-{(int(match[1]) % 200) + 1:05d}"
            require(attention.neighbor.identifier == expected_neighbor,
                    f"La atención {attention.pk} tiene marca masiva pero su vecino difiere del seed.")
            attention_ids.append(attention.pk)

    tube_ids = []
    candidates = TubeEntry.objects.filter(
        Q(source_task_id__in=tasks) |
        Q(source_task__isnull=True, notes__startswith="Tarea migrada del Kanban (ID "),
    )
    for tube in candidates:
        match = LEGACY_NOTE.match(tube.notes)
        source_id = tube.source_task_id or (int(match[1]) if match else None)
        if source_id in tasks:
            require(tube.title == tasks[source_id] and tube.origin == TubeEntry.Origin.INTERNAL
                    and tube.channel == TubeEntry.Channel.DELEGATION,
                    f"El tubo {tube.pk} vinculado a una tarea masiva tiene datos inesperados.")
            tube_ids.append(tube.pk)

    activities = Activity.objects.filter(task__in=task_qs)
    require(not activities.exclude(name__regex=r"^Actividad masiva #[0-9]{4}$").exists(),
            "Hay actividades sin marca de seed vinculadas a tareas masivas.")
    require(not Evidence.objects.filter(activity__in=activities).exclude(
        Q(image_url__regex=r"^https://ejemplo\.cl/evidencias/masiva-[0-9]{5}\.jpg$") &
        (Q(file="") | Q(file__isnull=True)),
    ).exists(), "Hay evidencias ajenas al seed vinculadas a las actividades masivas.")

    collector = Collector(using=connection.alias)
    collector.collect(task_qs)
    collector.collect(TubeEntry.objects.filter(pk__in=tube_ids, source_task__isnull=True))
    collector.collect(Attention.objects.filter(pk__in=attention_ids))
    ids = {model: {row.pk for row in rows} for model, rows in collector.data.items()}
    for queryset in collector.fast_deletes:
        ids.setdefault(queryset.model, set()).update(queryset.values_list("pk", flat=True))
    ids = {model: pks for model, pks in ids.items() if pks}
    allowed = {Task, TubeEntry, Activity, Evidence, TubeStatusChange, Attention}
    require(set(ids) <= allowed and not collector.field_updates,
            "La limpieza afectaría registros ajenos al lote, como comentarios, gestiones o reasignaciones.")
    require(ids.get(TubeEntry, set()) == set(tube_ids), "Se detectaron tubos adicionales en cascada.")
    return collector, ids


def database_target(allow_env_db):
    vendor = connection.vendor
    name = connection.settings_dict["NAME"]
    local = Path(__file__).resolve().parents[1] / "db.sqlite3"
    require(vendor in {"sqlite", "mysql", "postgresql"}, f"Motor sin respaldo implementado: {vendor}.")
    require(name and name != ":memory:" and (vendor != "sqlite" or not str(name).startswith("file:")),
            "Se requiere una base de datos persistente.")
    require(allow_env_db or (vendor == "sqlite" and Path(name).resolve() == local),
            "Usa --allow-env-db para seleccionar explícitamente la base Django configurada.")
    host = connection.settings_dict.get("HOST") or "local"
    print(f"Destino Django: {vendor} · {host} · {name}", flush=True)


def run_dump(command, **kwargs):
    require(subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kwargs).returncode == 0,
            f"Falló {Path(command[0]).name}; revisa permisos, conexión y versión del cliente.")


def mysql_backup(path):
    tool = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    require(tool is not None, "Instala el cliente mariadb-dump o mysqldump.")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' AND ENGINE <> 'InnoDB'"
        )
        require(not cursor.fetchall(), "La base tiene tablas no transaccionales; se cancela la operación.")
    params = connection.get_connection_params()
    keys = {"user": "user", "password": "password", "passwd": "password",
            "host": "host", "port": "port", "unix_socket": "socket"}
    credentials = {}
    for key, option in keys.items():
        if params.get(key):
            credentials[option] = params[key]
    for key, value in (params.get("ssl") or {}).items():
        require(key in {"ca", "capath", "cert", "key", "cipher"}, f"Opción TLS sin soporte: {key}.")
        credentials[f"ssl-{key}"] = value
    if params.get("ssl_mode"):
        credentials["ssl-mode"] = params["ssl_mode"]
    with tempfile.TemporaryDirectory() as folder:
        config = Path(folder) / "client.cnf"
        with os.fdopen(os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as file:
            file.write("[client]\n")
            for key, value in credentials.items():
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
                file.write(f'{key}="{escaped}"\n')
        run_dump([tool, f"--defaults-file={config}", "--single-transaction", "--quick", "--skip-lock-tables",
                  "--no-tablespaces", "--hex-blob", "--default-character-set=utf8mb4",
                  f"--result-file={path}", "--", str(connection.settings_dict["NAME"])])
    with path.open("rb") as file:
        file.seek(max(0, path.stat().st_size - 8192))
        require(b"-- Dump completed on " in file.read(), "El volcado SQL no contiene su marca de finalización.")


def postgres_backup(path):
    dump, restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    require(dump and restore, "Instala los clientes pg_dump y pg_restore.")
    params = connection.get_connection_params()
    variables = {"host": "PGHOST", "port": "PGPORT", "user": "PGUSER", "password": "PGPASSWORD",
                 "sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY"}
    env = {**os.environ, **{key: str(params[param]) for param, key in variables.items() if params.get(param)}}
    run_dump([dump, "--no-password", "--format=custom", f"--file={path}",
              f"--dbname={connection.settings_dict['NAME']}"], env=env)
    run_dump([restore, "--list", str(path)])


def backup(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    suffix = {"sqlite": "sqlite3", "mysql": "sql", "postgresql": "dump"}[connection.vendor]
    path = directory / f"antes-actividad-masiva-{timezone.now():%Y%m%d-%H%M%S-%f}.{suffix}"
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    try:
        if connection.vendor == "sqlite":
            connection.ensure_connection()
            with closing(sqlite3.connect(path)) as destination:
                connection.connection.backup(destination)
                require(destination.execute("PRAGMA integrity_check").fetchone() == ("ok",), "Respaldo inválido.")
        elif connection.vendor == "mysql":
            mysql_backup(path)
        else:
            postgres_backup(path)
        require(path.stat().st_size > 0, "El respaldo quedó vacío.")
    except Exception:
        path.unlink()
        raise
    print(f"Respaldo generado y comprobado: {path}", flush=True)


def historical_time(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def historical_save(record, moment):
    record.full_clean()
    record.save()
    type(record).objects.filter(pk=record.pk).update(created_at=moment, updated_at=moment)
    record.created_at = moment


def seed_inputs(period):
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
    return goals, subtypes, neighbors, employees


def seed(period, photos):
    goals, subtypes, neighbors, employees = seed_inputs(period)
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
            status=status, notes="Solicitud de demostración para el trimestre julio a septiembre.",
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


def verify_batch(period):
    tasks = Task.alive.filter(title__startswith=MARK)
    tubes = TubeEntry.alive.filter(title__startswith=MARK)
    attentions = Attention.alive.filter(description__startswith=MARK)
    start, _ = rules.day_bounds(period.start_date)
    _, end = rules.day_bounds(period.end_date)
    require(tasks.count() == tasks.filter(goal__period=period, due_date__range=(period.start_date, period.end_date)).count() == 25,
            "Las tareas nuevas no corresponden al período.")
    require(tubes.count() == tubes.filter(tubos_originados_en(period),
            request_date__range=(period.start_date, period.end_date),
            due_date__range=(period.start_date, period.end_date)).count() == 60, "Los tubos nuevos no corresponden al período.")
    require(attentions.count() == attentions.filter(created_at__gte=start, created_at__lt=end).count() == 15,
            "Las atenciones nuevas no corresponden al período.")
    states = Counter(tubes.values_list("status", flat=True))
    require(states == dict.fromkeys(TUBE_STATES, 15), f"Distribución incorrecta: {states}.")
    require(tubes.filter(source_task__in=tasks).count() == 25, "Faltan tarjetas de agenda.")
    require(TubeStatusChange.objects.filter(entry__in=tubes).count() == 40, "Historial incompleto.")
    require(all(entry.completed_at and entry.proof_image and entry.proof_image.storage.exists(entry.proof_image.name)
                for entry in tubes.filter(status=TubeEntry.Status.DONE)), "Faltan respaldos de cierre.")


def already_loaded():
    return (Task.objects.filter(title__startswith=MARK).exists()
            or TubeEntry.objects.filter(title__startswith=MARK).exists()
            or Attention.objects.filter(description__startswith=MARK).exists())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-env-db", action="store_true", help="Autoriza el destino Django configurado.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Respalda y aplica el reemplazo.")
    mode.add_argument("--backup-only", action="store_true", help="Respalda sin cambiar datos.")
    parser.add_argument("--backup-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()

    database_target(args.allow_env_db)
    if args.backup_only:
        backup(args.backup_dir.resolve())
        return
    executor = MigrationExecutor(connection)
    require(not executor.migration_plan(executor.loader.graph.leaf_nodes()),
            "Hay migraciones pendientes. Respalda la base antes de ejecutar manage.py migrate.")
    periods = list(Period.alive.filter(name=PERIOD_NAME, start_date="2026-07-01", end_date="2026-09-30")[:2])
    require(len(periods) == 1, "Se requiere exactamente un período activo en el catálogo con el nombre y rango solicitados.")
    period = periods[0]
    if already_loaded():
        verify_batch(period)
        print("El lote de 100 registros ya existe y fue verificado. No hay cambios.")
        return
    seed_inputs(period)
    _, plan = old_records()
    counts = {model._meta.label_lower: len(ids) for model, ids in plan.items()}
    print(f"Eliminaciones previstas: {counts}. Carga: 60 tubos, 25 tareas y 15 atenciones.", flush=True)
    if not args.apply:
        return

    backup(args.backup_dir.resolve())
    protected = [get_user_model(), Employee, Neighbor, *apps.get_app_config("sgr_core").get_models()]
    photos = []
    try:
        with transaction.atomic():
            Period.objects.select_for_update().get(pk=period.pk)
            require(not already_loaded(), "El lote apareció tras el respaldo. Se cancela el reemplazo.")
            before = {model: set(model.objects.values_list("pk", flat=True)) for model in protected}
            for model, ids in plan.items():
                list(model.objects.filter(pk__in=ids).order_by("pk").select_for_update().values_list("pk", flat=True))
            collector, locked_plan = old_records()
            require(locked_plan == plan, "El lote cambió tras el respaldo. Vuelve a ejecutar la simulación.")
            _, deleted = collector.delete()
            require({label.lower(): count for label, count in deleted.items()} == counts,
                    f"Borrado inesperado: {deleted}.")
            seed(period, photos)
            verify_batch(period)
            require(all(ids == set(model.objects.values_list("pk", flat=True)) for model, ids in before.items()),
                    "Cambió un catálogo o un padrón protegido.")
            if connection.vendor == "sqlite":
                connection.check_constraints()
    except Exception:
        for photo in photos:
            photo.storage.delete(photo.name)
        raise
    print(f"Confirmado. Eliminados: {deleted}. Creados: 60 tubos, 25 tareas, 15 atenciones y 40 historiales.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        sys.exit(str(exc))
