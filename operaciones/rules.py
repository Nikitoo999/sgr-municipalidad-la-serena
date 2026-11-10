"""Reglas de negocio del módulo de Atenciones (Bloque 2B).

Se centralizan aquí para que el formulario, las vistas y los futuros reportes
de puntaje usen exactamente la misma lógica:

- **Tope diario**: cada funcionario puede ingresar como máximo
  ``DAILY_ATTENTION_LIMIT`` (7) atenciones por día, en hora de Chile. No
  aplica al superadministrador (cuenta técnica del sistema).
- **Gestiones de seguimiento**: hasta ``MAX_FOLLOW_UPS`` (3) por atención.
  Una gestión registra lo que se hizo después del ingreso; NO es una atención
  nueva, así que no suma al puntaje operativo ni cuenta para el tope diario.
- **Cierre semanal**: la semana va de lunes a domingo. Con la semana cerrada
  para una delegación no se pueden ingresar ni editar atenciones de esa
  semana en esa delegación (ni registrar gestiones mientras la semana
  actual esté cerrada).
- **Puntaje operativo**: solo suman las atenciones vivas con
  ``counts_for_score``. Las ingresadas por el rol Delegado (alcance "Su
  delegación") se marcan al crearlas como que no cuentan.
"""

from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

#: Máximo de atenciones que un funcionario puede ingresar en un día.
DAILY_ATTENTION_LIMIT = 7
#: Máximo de gestiones de seguimiento por atención.
MAX_FOLLOW_UPS = 3
#: Alcances de rol cuyos ingresos NO suman al puntaje operativo (Delegado).
NON_SCORING_SCOPES = ("own_delegation",)
#: Estados en que una atención sigue abierta y admite gestiones.
OPEN_STATUSES = ("received", "in_progress")


# ---------------------------------------------------------------------------
# Fechas y semanas (hora local de Chile)
# ---------------------------------------------------------------------------


def local_day(value=None):
    """Fecha local (America/Santiago) de un datetime, o la de hoy."""
    if value is None:
        return timezone.localdate()
    return timezone.localtime(value).date()


def day_bounds(day):
    """``(inicio, fin)`` del día local como datetimes con zona horaria."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end


def week_start(day):
    """Lunes de la semana de ``day``."""
    return day - timedelta(days=day.weekday())


def week_bounds(start):
    """``(inicio, fin)`` de la semana que empieza el lunes ``start``."""
    begin, _ = day_bounds(start)
    _, end = day_bounds(start + timedelta(days=6))
    return begin, end


def week_label(start):
    """"02-11-2026 al 08-11-2026"."""
    return f"{start:%d-%m-%Y} al {start + timedelta(days=6):%d-%m-%Y}"


# ---------------------------------------------------------------------------
# Tope diario de ingresos
# ---------------------------------------------------------------------------


def daily_limit():
    """Tope diario (configurable con ``ATTENTION_DAILY_LIMIT`` en settings)."""
    return int(getattr(settings, "ATTENTION_DAILY_LIMIT", DAILY_ATTENTION_LIMIT))


def applies_daily_limit(user):
    """El tope aplica a todo funcionario; no al superadministrador."""
    return (
        user is not None
        and getattr(user, "is_authenticated", False)
        and not getattr(user, "is_superuser", False)
    )


def attentions_entered_on(user, day=None):
    """Atenciones vivas que ``user`` ingresó en el día local ``day`` (hoy)."""
    from .models import Attention

    start, end = day_bounds(day or local_day())
    return Attention.alive.filter(
        responsible_id=user.pk, created_at__gte=start, created_at__lt=end,
    )


def daily_limit_error(user, lock=False):
    """Mensaje si ``user`` ya alcanzó el tope de hoy; si no, cadena vacía.

    Con ``lock=True`` (dentro de ``transaction.atomic()``) se bloquea la fila
    del usuario con ``select_for_update`` para que dos ingresos simultáneos no
    pasen ambos el control (en MariaDB; SQLite ya serializa las escrituras).
    """
    if not applies_daily_limit(user):
        return ""
    if lock:
        list(
            get_user_model().objects.select_for_update()
            .filter(pk=user.pk).values_list("pk", flat=True)
        )
    limit = daily_limit()
    if attentions_entered_on(user).count() >= limit:
        return (
            f"Alcanzaste el máximo de {limit} atenciones ingresadas hoy. Si el "
            "vecino vuelve por el mismo caso, registra una gestión de seguimiento "
            "en su atención: las gestiones no cuentan como un ingreso nuevo."
        )
    return ""


# ---------------------------------------------------------------------------
# Puntaje operativo
# ---------------------------------------------------------------------------


def counts_for_score(user):
    """¿Las atenciones que ingresa ``user`` suman al puntaje operativo?

    No suman las del rol Delegado (alcance "Su delegación"): supervisa a su
    equipo y sus ingresos no se cuentan como producción propia.
    """
    employee = getattr(user, "employee", None)
    role = getattr(employee, "role", None) if employee is not None else None
    return not (role is not None and role.scope in NON_SCORING_SCOPES)


def scoring_attentions(queryset=None):
    """Atenciones que suman al puntaje operativo.

    Solo atenciones vivas con ``counts_for_score``. Las gestiones de
    seguimiento (``AttentionFollowUp``) nunca suman: no son atenciones nuevas.
    """
    from .models import Attention

    queryset = Attention.alive.all() if queryset is None else queryset
    return queryset.filter(counts_for_score=True)


# ---------------------------------------------------------------------------
# Cierre semanal
# ---------------------------------------------------------------------------


def closure_for(delegation_id, day):
    """Cierre vigente de la semana de ``day`` en la delegación (o ``None``)."""
    from .models import WeeklyClosure

    if not delegation_id or day is None:
        return None
    return WeeklyClosure.alive.filter(
        delegation_id=delegation_id, week_start=week_start(day),
    ).first()


def is_week_closed(delegation_id, day):
    return closure_for(delegation_id, day) is not None


def attention_closure(attention):
    """Cierre que bloquea la atención (semana de su ingreso), o ``None``."""
    if attention is None or attention.created_at is None:
        return None
    return closure_for(attention.delegation_id, local_day(attention.created_at))


def closed_pairs(attentions):
    """``{(delegation_id, lunes)}`` cerrados entre ``attentions`` (1 consulta)."""
    from .models import WeeklyClosure

    pairs = {
        (item.delegation_id, week_start(local_day(item.created_at)))
        for item in attentions
        if item.created_at is not None and item.delegation_id
    }
    if not pairs:
        return set()
    closed = WeeklyClosure.alive.filter(
        delegation_id__in={delegation for delegation, _ in pairs},
        week_start__in={start for _, start in pairs},
    ).values_list("delegation_id", "week_start")
    return set(closed) & pairs


def close_week(delegation, start, user, notes=""):
    """Cierra la semana ``start`` (lunes) de la delegación.

    Devuelve ``(cierre, cerrada_ahora)``. Si la semana se había reabierto, el
    mismo registro vuelve a quedar vigente (la restricción única es por
    delegación y semana).
    """
    from .models import WeeklyClosure

    with transaction.atomic():
        closure, created = WeeklyClosure.objects.select_for_update().get_or_create(
            delegation=delegation, week_start=start,
            defaults={"closed_by": user, "notes": notes},
        )
        if created:
            return closure, True
        if closure.deleted_at is None:
            return closure, False
        closure.deleted_at = None
        closure.closed_by = user
        closure.closed_at = timezone.now()
        closure.notes = notes
        closure.save()
        return closure, True


def reopen_week(closure):
    """Reabre una semana (borrado lógico del cierre; queda en la auditoría)."""
    closure.deleted_at = timezone.now()
    closure.save(update_fields=["deleted_at", "updated_at"])


def week_summary(delegation_id, start):
    """Atenciones ingresadas en la semana y cuántas suman al puntaje."""
    from django.db.models import Count, Q

    from .models import Attention

    begin, end = week_bounds(start)
    return Attention.alive.filter(
        delegation_id=delegation_id, created_at__gte=begin, created_at__lt=end,
    ).aggregate(
        total=Count("pk"),
        puntaje=Count("pk", filter=Q(counts_for_score=True)),
    )


# ---------------------------------------------------------------------------
# Gestiones de seguimiento
# ---------------------------------------------------------------------------


def follow_up_block_reason(attention):
    """Motivo por el que no se puede registrar otra gestión ("" si se puede)."""
    count = attention.follow_ups.count()
    if count >= MAX_FOLLOW_UPS:
        return (
            f"La atención {attention.number} ya tiene las {MAX_FOLLOW_UPS} "
            "gestiones de seguimiento permitidas."
        )
    if attention.status not in OPEN_STATUSES:
        return (
            f"La atención está «{attention.get_status_display()}»: para registrar "
            "otra gestión debe volver a «Ingresada» o «En gestión»."
        )
    closure = closure_for(attention.delegation_id, local_day())
    if closure is not None:
        return (
            f"La semana actual ({week_label(closure.week_start)}) está cerrada "
            "para esta delegación: no se pueden registrar gestiones."
        )
    return ""


def register_follow_up(attention, user, description):
    """Registra la siguiente gestión (1, 2 o 3) de la atención.

    Bloquea la fila de la atención mientras calcula el correlativo, así dos
    registros simultáneos no superan el máximo (además, la base de datos lo
    garantiza con la restricción única y el CHECK 1..3). Lanza
    ``ValidationError`` si no se puede registrar.
    """
    from .models import Attention, AttentionFollowUp

    with transaction.atomic():
        locked = Attention.objects.select_for_update().get(pk=attention.pk)
        reason = follow_up_block_reason(locked)
        if reason:
            raise ValidationError(reason)
        return AttentionFollowUp.objects.create(
            attention=locked,
            sequence=locked.follow_ups.count() + 1,
            description=description,
            performed_by=user,
        )
