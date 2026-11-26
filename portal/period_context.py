"""Selección global de período y alcance temporal de los registros operativos."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View

from operaciones.calculos import periodo_vigente
from operaciones.models import Attention
from operaciones.periodos import TUBO_ABIERTO, periodo_anterior, tubos_originados_en
from operaciones.rules import day_bounds
from sgr_core.models import Period

from . import access

SESSION_KEY = "active_period_id"
LEGACY_PARAMS = {"goals": "periodo", "achievements": "periodo", "reports": "period"}


def available_periods():
    return Period.alive.order_by("-start_date", "-pk")


def active_delegation_id(request):
    delegation = access.get_active_delegation(request)
    return getattr(delegation, "pk", None)


def _requested_period(value):
    if value and len(str(value)) <= 19 and str(value).isascii() and str(value).isdigit():
        pk = int(value)
        if pk <= 2**63 - 1:
            return available_periods().filter(pk=pk).first()
    return None


def active_period(request):
    if not hasattr(request, "_sgr_period"):
        route = getattr(request, "resolver_match", None)
        parameter = LEGACY_PARAMS.get(route.url_name) if route else None
        selected = _requested_period(request.GET.get(parameter)) if parameter else None
        if selected is not None:
            request.session[SESSION_KEY] = selected.pk
        request._sgr_period = (
            selected or _requested_period(request.session.get(SESSION_KEY))
            or periodo_vigente(timezone.localdate())
        )
    return request._sgr_period


class SwitchPeriodView(LoginRequiredMixin, View):
    def post(self, request):
        period = _requested_period(request.POST.get("period"))
        if period is None:
            messages.error(request, "El período seleccionado no está disponible.")
        else:
            request.session[SESSION_KEY] = period.pk
        return redirect("home")


def _own_filters(period):
    start, _ = day_bounds(period.start_date)
    _, end = day_bounds(period.end_date)
    return {
        "tasks": Q(goal__period=period),
        "attentions": Q(created_at__gte=start, created_at__lt=end),
        "tubes": tubos_originados_en(period),
    }


def _operational_querysets(request):
    from .agenda_views import tareas_del_alcance
    from .crud.attentions import attentions_scope
    from .tubes_views import tubos_del_alcance

    return {
        "tasks": tareas_del_alcance(request).filter(goal__deleted_at__isnull=True),
        "attentions": attentions_scope(request, Attention.alive.all()),
        "tubes": tubos_del_alcance(request),
    }


def operational_records(request):
    """Registros visibles, antes de aplicar filtros de cada pantalla."""
    if hasattr(request, "_sgr_operational_records"):
        return request._sgr_operational_records

    scoped = _operational_querysets(request)
    period = active_period(request)
    if period is None:
        request._sgr_operational_records = scoped
        return scoped

    filters = _own_filters(period)
    records = {key: qs.filter(filters[key]) for key, qs in scoped.items()}
    today = timezone.localdate()
    if period.status == "En curso" and period.start_date <= today <= period.end_date:
        permissions = access.get_access(request)
        visible = (
            (permissions.can("tasks", "view"), records["tasks"]),
            (permissions.can("attentions", "view"), records["attentions"]),
            (permissions.can("achievements", "view"), records["tubes"]),
        )
        if not any(allowed and qs.exists() for allowed, qs in visible):
            previous = periodo_anterior(period)
            if previous is not None:
                filters = _own_filters(previous)
                records["tasks"] = scoped["tasks"].filter(
                    filters["tasks"], due_date__lt=today,
                ).exclude(status="Completada")
                records["tubes"] = scoped["tubes"].filter(
                    filters["tubes"], due_date__lt=today, status__in=TUBO_ABIERTO,
                )
    request._sgr_operational_records = records
    return records
