"""Cumplimiento de la matriz por funcionario, con semáforo (3.6)."""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from operaciones.calculos import TOPE_CUMPLIMIENTO, calcular_cumplimiento, dias_libres
from sgr_core.models import Period

from .access import ModulePermissionMixin
from .goals_views import elegir_periodo, funcionarios_del_alcance
from .modules import MODULE_ICONS, MODULE_LABELS

DECIMO = Decimal("0.1")


class ComplianceView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/compliance.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodos = list(Period.objects.filter(deleted_at__isnull=True).order_by("-start_date"))
        periodo = elegir_periodo(self.request, periodos)

        filas = []
        if periodo:
            hoy = timezone.localdate()
            for emp in funcionarios_del_alcance(self.request):
                cumplimiento = calcular_cumplimiento(emp, periodo, hoy)
                for fila in cumplimiento["items"]:
                    logro = min(fila["razon"], TOPE_CUMPLIMIENTO) * 100
                    fila["logro_pct"] = logro.quantize(DECIMO)
                filas.append({
                    "empleado": emp,
                    "libres": len(dias_libres(emp, periodo)),
                    "cumplimiento": cumplimiento,
                    "esperado_pct": (cumplimiento["esperado"] * 100).quantize(DECIMO),
                })

        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "module_icon": MODULE_ICONS["achievements"],
            "periodos": periodos,
            "periodo": periodo,
            "filas": filas,
            "tope_pct": int(TOPE_CUMPLIMIENTO * 100),
        })
        return context