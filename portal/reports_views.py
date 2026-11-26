"""Vista del módulo de Reportes (Block 3B) - SGR Municipalidad de La Serena."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from operaciones import calculos
from operaciones.models import Employee
from sgr_core.models import Delegation

from .access import ModulePermissionMixin, get_active_delegation, visible_users
from .modules import MODULE_ICONS, MODULE_LABELS
from .period_context import active_delegation_id, active_period, available_periods, operational_records

DELEGATE_POSITION_CODE = "CAR01"
REPORTS_MODULE = "reports"  # clave real en sgr_core.roles.MODULES
TEMPLATE_NAME = "portal/reports.html"


def _empleados_en_alcance(request):
    """Employees visibles según rango y delegación activa del usuario."""
    active = get_active_delegation(request)
    if active is None:
        return Employee.objects.none()

    qs = (
        Employee.objects.filter(
            deleted_at__isnull=True,
            user__is_active=True,
            user__in=visible_users(request.user),
        )
        .select_related("position", "user")
        .order_by("user__last_name", "user__first_name", "pk")
    )
    if isinstance(active, Delegation):  # 'ALL' no filtra por delegación
        qs = qs.filter(delegation=active)
    return qs


def _es_delegado(empleado):
    posicion = empleado.position
    return posicion is not None and posicion.code == DELEGATE_POSITION_CODE


class ReportsView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = TEMPLATE_NAME
    module = REPORTS_MODULE
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo = active_period(self.request)
        hoy = timezone.localdate()

        reporte_funcionarios = []
        if periodo is not None:
            delegation_id = active_delegation_id(self.request)
            tubos = operational_records(self.request)["tubes"]
            for empleado in _empleados_en_alcance(self.request):
                ingresos = calculos.ingresos_por_dia(empleado, periodo, delegation_id=delegation_id)
                sin_ingresar = calculos.dias_sin_ingresar(empleado, periodo, hoy, delegation_id=delegation_id)
                sobre_limite = calculos.dias_sobre_el_limite(empleado, periodo, delegation_id=delegation_id)
                cumplimiento = calculos.calcular_cumplimiento(
                    empleado, periodo, hoy, delegation_id=delegation_id, tubos=tubos,
                )
                reporte_funcionarios.append(
                    {
                        "employee": empleado,
                        "es_delegado": _es_delegado(empleado),
                        "ingresos": ingresos,                      # Counter {fecha: cantidad}
                        "total_ingresos": sum(ingresos.values()),
                        "dias_sin_ingresar": sin_ingresar,         # lista de fechas
                        "dias_sobre_limite": sobre_limite,         # lista de fechas
                        "cumplimiento": cumplimiento,              # dict (ver calcular_cumplimiento)
                    }
                )

        # Ranking: solo evaluados (con cargo y sin la posición CAR01), mayor % primero.
        ranking = sorted(
            (
                fila for fila in reporte_funcionarios
                if fila["employee"].position_id is not None and not fila["es_delegado"]
            ),
            key=lambda fila: fila["cumplimiento"]["porcentaje"],
            reverse=True,
        )

        context.update(
            {
                "active_module": "reports",
                "module_label": MODULE_LABELS["reports"],
                "module_icon": MODULE_ICONS["reports"],
                "periodo": periodo,
                "periodos": available_periods(),
                "reporte_funcionarios": reporte_funcionarios,
                "ranking": ranking,
                "sin_registros": not any(
                    fila["total_ingresos"] or fila["cumplimiento"]["items"]
                    for fila in reporte_funcionarios
                ),
            }
        )
        return context

class ReportsChartsView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Gráficos y ritmo del período (HU-17, preview de implementación)."""

    template_name = "portal/reports_charts.html"
    module = REPORTS_MODULE
    action = "view"

    def get_context_data(self, **kwargs):
        from .dashboard import barras_items, estado_tubos, ritmo_del_periodo, serie_ritmo

        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        ritmo = ritmo_del_periodo(self.request, hoy)
        serie = None
        if ritmo and not ritmo.get("sin_datos"):
            serie = serie_ritmo(
                ritmo["empleados"], ritmo["periodo"], hoy, ritmo["cumplimientos"],
                delegation_id=active_delegation_id(self.request),
            )
        context.update({
            "active_module": "reports",
            "module_label": MODULE_LABELS["reports"],
            "module_icon": MODULE_ICONS["reports"],
            "ritmo": ritmo,
            "serie": serie,
            "items": barras_items(ritmo),
            "tubos": estado_tubos(self.request),
        })
        return context
