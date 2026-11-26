"""Períodos de medición: cierre de trimestre y traspaso con prioridad.

Regla del preview de implementación ("Cierre de Trimestre y Traspaso con
Prioridad"): al cerrar el trimestre, las solicitudes del tubo y las atenciones
que siguen abiertas pasan al siguiente trimestre marcadas como PRIORITARIAS y
generan un aviso visible en la barra superior y en Inicio.

RN-013 (Guía): un período cerrado no se modifica salvo reapertura autorizada
y auditada. La reapertura no quita las prioridades ya traspasadas.
"""

from calendar import monthrange
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q

from sgr_core.models import Period

MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
#: Estados abiertos de una solicitud del tubo y de una atención.
TUBO_ABIERTO = ("received", "pending", "in_progress")
ATENCION_ABIERTA = ("received", "in_progress")


def nombre_trimestre(inicio):
    """"Trimestre Ene-Mar 2027" para el trimestre que contiene ``inicio``."""
    q = (inicio.month - 1) // 3 + 1
    return f"Trimestre {MESES[3 * q - 3]}-{MESES[3 * q - 1]} {inicio.year}"


def fechas_trimestre(dia):
    """(inicio, fin, número) del trimestre calendario que contiene ``dia``."""
    q = (dia.month - 1) // 3 + 1
    inicio = date(dia.year, 3 * q - 2, 1)
    fin = date(dia.year, 3 * q, monthrange(dia.year, 3 * q)[1])
    return inicio, fin, q


def dias_computables(period):
    """Días hábiles (lunes a viernes) del período (RF-005)."""
    total, dia = 0, period.start_date
    while dia <= period.end_date:
        if dia.weekday() < 5:
            total += 1
        dia += timedelta(days=1)
    return total


def periodo_siguiente(period):
    """Período vivo que empieza después de ``period`` (o ``None``)."""
    return (
        Period.objects.filter(deleted_at__isnull=True, start_date__gt=period.end_date)
        .order_by("start_date", "pk").first()
    )


def periodo_anterior(period):
    """Período más cercano que termina antes del inicio del seleccionado."""
    return Period.alive.filter(end_date__lt=period.start_date).order_by("-end_date", "-pk").first()


def tubos_originados_en(period):
    """Período de la meta para tareas vinculadas y fecha para solicitudes directas."""
    return Q(source_task__goal__period=period) | Q(
        source_task__isnull=True, request_date__range=(period.start_date, period.end_date),
    )


def crear_siguiente(period):
    """Crea el trimestre calendario que sigue a ``period`` ("En curso")."""
    inicio, fin, q = fechas_trimestre(period.end_date + timedelta(days=1))
    return Period.objects.create(
        name=nombre_trimestre(inicio), start_date=inicio, end_date=fin, quarter=q, status="En curso",
    )


def pendientes(period, delegation_ids=None):
    """(tubos, atenciones) abiertos del período.

    Tubos: solicitados dentro del período o traspasados a él. Atenciones:
    ingresadas dentro del período y aún abiertas.
    """
    from operaciones.models import Attention, TubeEntry
    from operaciones.rules import day_bounds

    tubos = TubeEntry.alive.filter(source_task__deleted_at__isnull=True, status__in=TUBO_ABIERTO).filter(
        tubos_originados_en(period) | Q(carried_to_period=period)
    )
    inicio, _ = day_bounds(period.start_date)
    _, fin = day_bounds(period.end_date)
    atenciones = Attention.alive.filter(
        status__in=ATENCION_ABIERTA, created_at__gte=inicio, created_at__lt=fin,
    )
    if delegation_ids is not None:
        tubos = tubos.filter(delegation_id__in=delegation_ids)
        atenciones = atenciones.filter(delegation_id__in=delegation_ids)
    return tubos, atenciones


@transaction.atomic
def cerrar_trimestre(period, destino, user):
    """Cierra ``period`` y traspasa sus pendientes a ``destino`` con prioridad.

    Devuelve ``{"tubos": n, "atenciones": m, "avisos": k}``.
    """
    from operaciones.models import Notice, TubeStatusChange

    locked = Period.objects.select_for_update().get(pk=period.pk)
    if locked.status == "Cerrado":
        raise ValueError(f"El período «{locked.name}» ya está cerrado.")
    if destino.pk == locked.pk or destino.start_date <= locked.end_date:
        raise ValueError("El período de destino debe ser posterior al que se cierra.")

    tubos, atenciones = pendientes(locked)
    motivo = f"Traspaso con prioridad desde {locked.name}"
    por_delegacion = {}
    for fila in tubos.values("delegation_id").annotate(n=Count("pk")):
        por_delegacion.setdefault(fila["delegation_id"], [0, 0])[0] = fila["n"]
    for fila in atenciones.values("delegation_id").annotate(n=Count("pk")):
        por_delegacion.setdefault(fila["delegation_id"], [0, 0])[1] = fila["n"]

    n_tubos = 0
    for entrada in tubos.select_for_update(of=("self",)):
        entrada.priority = True
        entrada.priority_reason = motivo
        entrada.carried_to_period = destino
        entrada.save(update_fields=["priority", "priority_reason", "carried_to_period", "updated_at"])
        TubeStatusChange.objects.create(
            entry=entrada, kind=TubeStatusChange.Kind.PRIORITY, from_value=locked.name[:80],
            to_value=destino.name[:80], notes=motivo, changed_by=user,
        )
        n_tubos += 1
    n_atenciones = atenciones.update(priority=True, priority_reason=motivo)

    locked.status = "Cerrado"
    locked.save(update_fields=["status", "updated_at"])

    avisos = 0
    for delegation_id, (nt, na) in por_delegacion.items():
        partes = []
        if nt:
            partes.append(f"{nt} solicitud{'es' if nt != 1 else ''} del tubo")
        if na:
            partes.append(f"{na} atenci{'ones' if na != 1 else 'ón'}")
        Notice.objects.create(
            kind=Notice.Kind.TRANSFER, delegation_id=delegation_id, created_by=user,
            title=f"Traspaso a {destino.name}: {' y '.join(partes)} con prioridad",
            text=(
                f"Al cerrar {locked.name} quedaron abiertas {' y '.join(partes)}. Pasan a "
                f"{destino.name} marcadas como PRIORITARIAS: revísalas primero."
            ),
            url="/cumplimiento/tubos/?prio=1" if nt else "/atenciones/",
        )
        avisos += 1
    if not por_delegacion:
        Notice.objects.create(
            kind=Notice.Kind.TRANSFER, created_by=user,
            title=f"{locked.name} cerrado sin pendientes",
            text=f"No quedaron solicitudes ni atenciones abiertas. El trimestre vigente es {destino.name}.",
        )
        avisos = 1
    return {"tubos": n_tubos, "atenciones": n_atenciones, "avisos": avisos}


@transaction.atomic
def reabrir(period):
    """Reabre un período cerrado (la auditoría la registra la vista)."""
    locked = Period.objects.select_for_update().get(pk=period.pk)
    if locked.status != "Cerrado":
        raise ValueError(f"El período «{locked.name}» no está cerrado.")
    locked.status = "En curso"
    locked.save(update_fields=["status", "updated_at"])
    return locked
