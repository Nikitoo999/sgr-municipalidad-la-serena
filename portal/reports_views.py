"""Vista del módulo de Reportes (Block 3B) - SGR Municipalidad de La Serena."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from operaciones import calculos
from operaciones.models import Employee
from sgr_core.models import Delegation, Period

from .access import ModulePermissionMixin, get_active_delegation, visible_users

DELEGATE_POSITION_CODE = "CAR01"
REPORTS_MODULE = "reports"  # clave real en sgr_core.roles.MODULES
TEMPLATE_NAME = "portal/reports.html"


def _resolver_periodo(request):
    """Periodo por ?period=ID; si falta o es inválido, el más reciente disponible."""
    period_id = request.GET.get("period")
    if period_id:
        try:
            periodo = Period.alive.filter(pk=int(period_id)).first()
        except (TypeError, ValueError):
            periodo = None
        if periodo is not None:
            return periodo
    return Period.alive.order_by("-start_date", "-pk").first()


def _empleados_en_alcance(request):
    """Employees visibles según rango y delegación activa del usuario."""
    active = get_active_delegation(request)
    if active is None:
        return Employee.objects.none()

    qs = (
        Employee.objects.filter(user__in=visible_users(request.user))
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
        periodo = _resolver_periodo(self.request)
        hoy = timezone.localdate()

        reporte_funcionarios = []
        if periodo is not None:
            for empleado in _empleados_en_alcance(self.request):
                ingresos = calculos.ingresos_por_dia(empleado, periodo)
                sin_ingresar = calculos.dias_sin_ingresar(empleado, periodo, hoy)
                sobre_limite = calculos.dias_sobre_el_limite(empleado, periodo)
                cumplimiento = calculos.calcular_cumplimiento(empleado, periodo, hoy)
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

        # Ranking: solo evaluados (excluye la posición CAR01), mayor % primero.
        ranking = sorted(
            (fila for fila in reporte_funcionarios if not fila["es_delegado"]),
            key=lambda fila: fila["cumplimiento"]["porcentaje"],
            reverse=True,
        )

        context.update(
            {
                "periodo": periodo,
                "periodos": Period.alive.order_by("-start_date"),
                "reporte_funcionarios": reporte_funcionarios,
                "ranking": ranking,
            }
        )
        return context