"""Cumplimiento de la matriz por funcionario, con semáforo (3.6)."""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from operaciones.calculos import TOPE_CUMPLIMIENTO, calcular_cumplimiento, dias_libres
from sgr_core.models import Period

"""Cumplimiento de la matriz por funcionario: semáforo, felicitaciones y reclamos (3.6)."""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from operaciones.calculos import (
    MAX_FELICITACIONES, PUNTOS_FELICITACION, PUNTOS_RECLAMO, TOPE_CUMPLIMIENTO,
    calcular_cumplimiento, dias_libres,
)
from operaciones.models import EmployeeFeedback
from sgr_core.models import Period

from . import access
from .access import ModulePermissionMixin
from .audit import audit
from .goals_views import elegir_periodo, funcionarios_del_alcance
from .modules import MODULE_ICONS, MODULE_LABELS

DECIMO = Decimal("0.1")


class ComplianceView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/compliance.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)
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
                comentarios = EmployeeFeedback.objects.filter(
                    employee=emp, deleted_at__isnull=True,
                    date__range=(periodo.start_date, periodo.end_date),
                ).order_by("-date", "-pk")
                filas.append({
                    "empleado": emp,
                    "libres": len(dias_libres(emp, periodo)),
                    "cumplimiento": cumplimiento,
                    "esperado_pct": (cumplimiento["esperado"] * 100).quantize(DECIMO),
                    "comentarios": list(comentarios),
                })

        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "module_icon": MODULE_ICONS["achievements"],
            "periodos": periodos,
            "periodo": periodo,
            "filas": filas,
            "tope_pct": int(TOPE_CUMPLIMIENTO * 100),
            "max_felicitaciones": MAX_FELICITACIONES,
            "puntos_felicitacion": PUNTOS_FELICITACION,
            "puntos_reclamo": PUNTOS_RECLAMO,
            "can_create": info.can("achievements", "create"),
        })
        return context


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = EmployeeFeedback
        fields = ["kind", "date", "description", "file"]


class FeedbackCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Registra una felicitación (con respaldo) o un reclamo sobre un funcionario."""

    module = "achievements"
    action = "create"

    def post(self, request, employee_id):
        empleado = get_object_or_404(funcionarios_del_alcance(request), pk=employee_id)
        if empleado.user_id == request.user.pk:
            raise PermissionDenied("No puedes registrar felicitaciones ni reclamos sobre ti mismo.")

        form = FeedbackForm(
            request.POST, request.FILES, instance=EmployeeFeedback(employee=empleado),
        )
        if form.is_valid():
            registro = form.save(commit=False)
            registro.registered_by = request.user
            registro.save()
            audit(
                request, "create", module="achievements",
                object_repr=f"{registro.get_kind_display()} de {empleado.full_name}",
                detail=f"Registrado por {request.user}",
            )
            messages.success(
                request, f"{registro.get_kind_display()} registrada para {empleado.full_name}.",
            )
        else:
            errores = "; ".join(e for lista in form.errors.values() for e in lista)
            messages.error(request, f"No se pudo registrar: {errores}")
        return redirect("achievements")