"""Alertas operativas (RF-037 / HU-31) y avisos de la barra superior.

Las alertas se calculan al vuelo según el alcance del usuario; solo se guarda
quién marcó cuál como revisada (``AlertReview``), sin borrar el evento.

Tipos:

- Compromisos del tubo vencidos o próximos a vencer (RF-019).
- Evidencias de la agenda y atenciones pendientes de validación (verificador).
- Registros propios rechazados o con corrección solicitada (funcionario).
- Ausencia de registros: funcionarios sin ingresos hace varios días hábiles
  (diapositiva 18; nuevo requerimiento, puntos 3 y 4).
- Avance bajo el umbral: funcionarios en rojo en el semáforo (HU-21).
- Días con ingresos sobre el tope de 7 (nuevo requerimiento, puntos 3 y 6:
  "registrar solo para cumplir").

Las de los tres primeros tipos son baratas y alimentan el contador de la
barra superior; las demás se calculan solo en la página de avisos.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from . import access

#: Días hábiles sin ingresos a partir de los cuales se alerta.
DIAS_SIN_INGRESO_ALERTA = 3
#: Días antes del compromiso en que se alerta.
DIAS_POR_VENCER = 3


@dataclass
class Alerta:
    key: str
    tipo: str
    nivel: str          # "alta" | "media" | "info"
    motivo: str
    responsable: str
    fecha: date
    url: str = ""
    extra: dict = field(default_factory=dict)


def _business_days_between(desde, hasta):
    """Días hábiles después de ``desde`` y hasta ``hasta`` (inclusive)."""
    total, dia = 0, desde + timedelta(days=1)
    while dia <= hasta:
        if dia.weekday() < 5:
            total += 1
        dia += timedelta(days=1)
    return total


def notices_for(request):
    """Avisos visibles para el usuario (globales o de sus delegaciones)."""
    from django.db.models import Q

    from operaciones.models import Notice

    user = request.user
    role = access.get_role(user)
    qs = Notice.objects.filter(deleted_at__isnull=True)
    if role is None:
        return qs.none()
    if role.scope == "all":
        return qs
    pks = [d.pk for d in access.allowed_delegations(user)]
    return qs.filter(Q(delegation__isnull=True) | Q(delegation_id__in=pks))


def alertas_baratas(request, hoy=None):
    """Alertas rápidas de calcular (también alimentan el contador)."""
    from operaciones.models import Attention, Evidence
    from operaciones.rules import is_verifier

    from .agenda_views import tareas_del_alcance
    from .crud.attentions import attentions_scope
    from .tubes_views import ABIERTOS, tubos_del_alcance

    hoy = hoy or timezone.localdate()
    user = request.user
    info = access.get_access(request)
    out = []

    if info.can("achievements", "view"):
        tubos = (
            tubos_del_alcance(request)
            .filter(status__in=ABIERTOS, due_date__isnull=False, due_date__lte=hoy + timedelta(days=DIAS_POR_VENCER))
            .select_related("responsible__user").order_by("due_date")[:100]
        )
        for t in tubos:
            vencido = t.due_date < hoy
            out.append(Alerta(
                key=f"tubo:{t.pk}:{t.due_date:%Y%m%d}",
                tipo="Compromiso vencido" if vencido else "Compromiso por vencer",
                nivel="alta" if vencido else "media",
                motivo=f"{t.code} · {t.title}: {'venció' if vencido else 'vence'} el {t.due_date:%d-%m-%Y}.",
                responsable=t.responsible.full_name if t.responsible_id else "Sin asignar",
                fecha=t.due_date, url=reverse("tube_detail", args=[t.pk]),
            ))

    verificador = is_verifier(user)
    if verificador and info.can("tasks", "edit"):
        evidencias = (
            Evidence.objects.filter(
                deleted_at__isnull=True, is_validated=False, review_status="pending",
                activity__task__in=tareas_del_alcance(request),
            )
            .exclude(activity__task__assigned_to__user_id=user.pk)
            .select_related("activity__task__assigned_to__user").order_by("created_at")[:100]
        )
        for ev in evidencias:
            asignado = ev.activity.task.assigned_to
            out.append(Alerta(
                key=f"evidencia:{ev.pk}", tipo="Evidencia por validar", nivel="media",
                motivo=f"{ev.activity.task.code} · {ev.activity.name}: evidencia sin revisar.",
                responsable=asignado.full_name if asignado else "Sin asignar",
                fecha=timezone.localtime(ev.created_at).date(), url=reverse("tasks"),
            ))
    if verificador and info.can("attentions", "edit"):
        from django.db.models import Q

        atenciones = (
            attentions_scope(request, Attention.alive.all())
            .filter(validation_status="pending", item__isnull=False, counts_for_score=True)
            .filter(~Q(evidence_image="") & Q(evidence_image__isnull=False) | ~Q(attachment="") & Q(attachment__isnull=False))
            .exclude(responsible_id=user.pk)
            .select_related("responsible").order_by("created_at")[:100]
        )
        for a in atenciones:
            out.append(Alerta(
                key=f"atencion:{a.pk}", tipo="Atención por validar", nivel="media",
                motivo=f"{a.number}: tiene evidencia y espera validación para sumar a la matriz.",
                responsable=a.responsible.get_full_name() or a.responsible.username,
                fecha=timezone.localtime(a.created_at).date(), url=reverse("attentions_detail", args=[a.pk]),
            ))

    # Lo propio rechazado o con corrección (para que el funcionario lo corrija).
    propias = Attention.alive.filter(responsible_id=user.pk, validation_status__in=("rejected", "correction"))[:50]
    for a in propias:
        out.append(Alerta(
            key=f"mi-atencion:{a.pk}:{a.validation_status}", tipo="Atención observada", nivel="alta",
            motivo=f"{a.number}: {a.get_validation_status_display().lower()}. {a.validation_notes}",
            responsable="Tú", fecha=timezone.localtime(a.validated_at or a.updated_at).date(),
            url=reverse("attentions_detail", args=[a.pk]),
        ))
    propias_ev = Evidence.objects.filter(
        deleted_at__isnull=True, review_status__in=("rejected", "correction"),
        activity__task__assigned_to__user_id=user.pk,
    ).select_related("activity__task")[:50]
    for ev in propias_ev:
        out.append(Alerta(
            key=f"mi-evidencia:{ev.pk}:{ev.review_status}", tipo="Evidencia observada", nivel="alta",
            motivo=f"{ev.activity.task.code} · {ev.activity.name}: {ev.get_review_status_display().lower()}. {ev.review_notes}",
            responsable="Tú", fecha=timezone.localtime(ev.validated_at or ev.updated_at).date(),
            url=reverse("tasks"),
        ))
    return out


def alertas_de_gestion(request, hoy=None):
    """Alertas que requieren calcular la matriz (solo en la página de avisos)."""
    from operaciones.calculos import (
        actividad_reciente, calcular_cumplimiento, dias_sobre_el_limite, periodo_vigente,
    )

    from .goals_views import funcionarios_del_alcance

    hoy = hoy or timezone.localdate()
    info = access.get_access(request)
    role = access.get_role(request.user)
    if not info.can("achievements", "view") or role is None or role.rank < 1:
        return []
    periodo = periodo_vigente(hoy)
    if periodo is None:
        return []
    out = []
    semana = hoy - timedelta(days=hoy.weekday())
    for emp in funcionarios_del_alcance(request)[:200]:
        if not emp.position.is_evaluated:
            continue
        reciente = actividad_reciente(emp, periodo, hoy)
        ultimo = reciente["ultimo"]
        sin = _business_days_between(ultimo, hoy) if ultimo else None
        if ultimo is None or sin >= DIAS_SIN_INGRESO_ALERTA:
            out.append(Alerta(
                key=f"sin-ingreso:{emp.pk}:{hoy:%Y%m%d}", tipo="Ausencia de registros", nivel="media",
                motivo=(f"Sin ingresos en el trimestre." if ultimo is None
                        else f"{sin} días hábiles sin ingresos (último: {ultimo:%d-%m-%Y})."),
                responsable=emp.full_name, fecha=hoy,
                url=reverse("achievements") + f"#func-{emp.pk}",
            ))
        cumplimiento = calcular_cumplimiento(emp, periodo, hoy)
        if cumplimiento["items"] and cumplimiento["semaforo"] == "rojo":
            out.append(Alerta(
                key=f"rojo:{emp.pk}:{periodo.pk}:{semana:%Y%m%d}", tipo="Avance bajo el umbral", nivel="alta",
                motivo=(f"Cumplimiento {cumplimiento['porcentaje']} % frente a "
                        f"{(cumplimiento['esperado'] * 100):.1f} % esperado a hoy (semáforo rojo)."),
                responsable=emp.full_name, fecha=hoy, url=reverse("achievements") + f"#func-{emp.pk}",
            ))
        sobre = [d for d in dias_sobre_el_limite(emp, periodo) if d >= semana - timedelta(days=7)]
        if sobre:
            out.append(Alerta(
                key=f"sobre-tope:{emp.pk}:{sobre[-1]:%Y%m%d}", tipo="Ingresos sobre el tope", nivel="info",
                motivo=(f"Más de 7 ingresos en un día ({', '.join(d.strftime('%d-%m') for d in sobre)}): "
                        "revisa si son registros reales o solo para cumplir."),
                responsable=emp.full_name, fecha=sobre[-1], url=reverse("reports"),
            ))
    return out


def reviewed_keys(user, keys):
    from operaciones.models import AlertReview

    if not keys:
        return set()
    return set(AlertReview.objects.filter(user=user, key__in=list(keys)).values_list("key", flat=True))


def badge_count(request):
    """Avisos no leídos + alertas rápidas sin revisar (contador de la barra)."""
    if not getattr(request.user, "is_authenticated", False) or access.get_role(request.user) is None:
        return 0
    cache = getattr(request, "_sgr_badge_count", None)
    if cache is not None:
        return cache
    no_leidos = notices_for(request).exclude(read_by=request.user).count()
    alertas = alertas_baratas(request)
    revisadas = reviewed_keys(request.user, [a.key for a in alertas])
    total = no_leidos + sum(1 for a in alertas if a.key not in revisadas)
    request._sgr_badge_count = total
    return total
