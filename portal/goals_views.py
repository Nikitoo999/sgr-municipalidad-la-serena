"""Metas por funcionario: asignación según cargo y trimestre (3.4)."""
from collections import defaultdict
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.views.generic import TemplateView

from operaciones.calculos import dias_habiles, dias_libres, factor_ajuste, meta_ajustada
from operaciones.models import Employee, EmployeeDayOff
from sgr_core.models import PositionItemGoal

from . import access
from .period_context import active_period, available_periods
from .access import ModulePermissionMixin
from .modules import MODULE_ICONS, MODULE_LABELS


def funcionarios_del_alcance(request):
    """Funcionarios con cargo, dentro del alcance del usuario y la delegación activa."""
    role = access.get_role(request.user)
    active = access.get_active_delegation(request)
    qs = Employee.objects.filter(
        deleted_at__isnull=True, user__is_active=True, position__isnull=False,
    ).select_related("user", "delegation", "position").prefetch_related(
        Prefetch("days_off", queryset=EmployeeDayOff.objects.filter(deleted_at__isnull=True)),
    )
    if role is None or active is None:
        return qs.none()
    if active != access.ALL_DELEGATIONS:
        qs = qs.filter(delegation_id=active.pk)
    if role.scope == "own_records":
        qs = qs.filter(user_id=request.user.pk)
    return qs.order_by("position__code", "user__first_name", "user__last_name")


class GoalsView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/goals.html"
    module = "goals"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodos = available_periods()
        periodo = active_period(self.request)

        metas = defaultdict(list)
        filas = []
        if periodo:
            goals = PositionItemGoal.objects.filter(
                period=periodo, deleted_at__isnull=True,
            ).select_related("item").order_by("item__code")
            for goal in goals:
                metas[goal.position_id].append(goal)

            total_habiles = len(dias_habiles(periodo.start_date, periodo.end_date))
            for emp in funcionarios_del_alcance(self.request):
                factor = factor_ajuste(emp, periodo)
                items, suma = [], Decimal("0")
                for goal in metas.get(emp.position_id, []):
                    items.append({
                        "nombre": goal.item.name,
                        "peso": goal.weight,
                        "meta": goal.target_value,
                        "ajustada": meta_ajustada(goal.target_value, factor),
                    })
                    suma += goal.weight
                filas.append({
                    "empleado": emp,
                    "libres": len(dias_libres(emp, periodo)),
                    "total_habiles": total_habiles,
                    "items": items,
                    "suma": suma,
                    "suma_ok": suma == Decimal("100"),
                })

        context.update({
            "active_module": "goals",
            "module_label": MODULE_LABELS["goals"],
            "module_icon": MODULE_ICONS["goals"],
            "periodos": periodos,
            "periodo": periodo,
            "filas": filas,
            "sin_registros": not any(fila["items"] for fila in filas),
        })
        return context
