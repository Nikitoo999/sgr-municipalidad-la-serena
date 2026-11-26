from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
"""Cumplimiento de la matriz por funcionario, con semáforo (3.6)."""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from operaciones.calculos import (
    MAX_FELICITACIONES, PUNTOS_FELICITACION, PUNTOS_RECLAMO, TOPE_CUMPLIMIENTO,
    actividad_reciente, calcular_cumplimiento, dias_libres, resumen_equipo,
)
from sgr_core.roles import SCOPE_RANKS

from . import access
from .access import ModulePermissionMixin
from .audit import audit
from .goals_views import funcionarios_del_alcance
from .period_context import active_delegation_id, active_period, available_periods, operational_records
from django.core.exceptions import PermissionDenied
from django.views import View
from operaciones.models import EmployeeDayOff, EmployeeFeedback
from .modules import MODULE_ICONS, MODULE_LABELS

DECIMO = Decimal("0.1")


class ComplianceView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/compliance.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)
        periodos = available_periods()
        periodo = active_period(self.request)

        filas = []
        if periodo:
            hoy = timezone.localdate()
            delegation_id = active_delegation_id(self.request)
            tubos = operational_records(self.request)["tubes"]
            for emp in funcionarios_del_alcance(self.request):
                cumplimiento = calcular_cumplimiento(emp, periodo, hoy, delegation_id=delegation_id, tubos=tubos)
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
                    "reciente": actividad_reciente(emp, periodo, hoy, delegation_id=delegation_id),
                })

        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "module_icon": MODULE_ICONS["achievements"],
            "periodos": periodos,
            "periodo": periodo,
            "filas": filas,
            "sin_registros": not any(
                fila["cumplimiento"]["items"] or fila["comentarios"] or fila["reciente"]["total"]
                for fila in filas
            ),
            "equipo": resumen_equipo(filas) if filas else None,
            "tope_pct": int(TOPE_CUMPLIMIENTO * 100),
            "max_felicitaciones": MAX_FELICITACIONES,
            "puntos_felicitacion": PUNTOS_FELICITACION,
            "puntos_reclamo": PUNTOS_RECLAMO,
            "can_create": puede_registrar_feedback(self.request),
            "tipos_dia_libre": EmployeeDayOff.Kind.choices,
        })
        return context


def puede_registrar_feedback(request):
    """Felicitaciones y reclamos los registra el delegado o un rol superior.

    Nuevo requerimiento (punto 8): la felicitación debe informarla el delegado;
    no puede venir del propio funcionario, aunque un rol personalizado le haya
    dado el permiso de crear en Cumplimiento.
    """
    role = access.get_role(request.user)
    return (
        role is not None
        and role.rank >= SCOPE_RANKS["own_delegation"]
        and access.get_access(request).can("achievements", "create")
    )


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = EmployeeFeedback
        fields = ["kind", "date", "description", "file"]


class FeedbackCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Registra una felicitación (con respaldo) o un reclamo sobre un funcionario."""

    module = "achievements"
    action = "create"

    def post(self, request, employee_id):
        if not puede_registrar_feedback(request):
            raise PermissionDenied(
                "Las felicitaciones y reclamos los registra el delegado o un rol superior."
            )
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


class DayOffForm(forms.ModelForm):
    class Meta:
        model = EmployeeDayOff
        fields = ["kind", "start_date", "end_date", "notes"]


class DayOffCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Registra días libres (vacaciones, licencia, administrativo...) de un funcionario.

    Nuevo requerimiento (punto 9): los ingresa el delegado en el semáforo para
    ajustar la meta del trimestre (``operaciones.calculos.factor_ajuste``).
    """

    module = "achievements"
    action = "create"

    def post(self, request, employee_id):
        if not puede_registrar_feedback(request):
            raise PermissionDenied("Los días libres los registra el delegado o un rol superior.")
        empleado = get_object_or_404(funcionarios_del_alcance(request), pk=employee_id)
        form = DayOffForm(request.POST, instance=EmployeeDayOff(employee=empleado))
        if form.is_valid():
            registro = form.save(commit=False)
            registro.registered_by = request.user
            registro.save()
            audit(
                request, "create", module="achievements",
                object_repr=f"{registro.get_kind_display()} de {empleado.full_name}",
                detail=f"{registro.start_date:%d-%m-%Y} a {registro.end_date:%d-%m-%Y}, registrado por {request.user}",
            )
            dias = registro.business_days
            messages.success(
                request,
                f"{registro.get_kind_display()} registrada para {empleado.full_name}: "
                f"{dias} día{'s' if dias != 1 else ''} hábil{'es' if dias != 1 else ''}. "
                "La meta del trimestre se ajustó.",
            )
        else:
            errores = "; ".join(e for lista in form.errors.values() for e in lista)
            messages.error(request, f"No se pudo registrar: {errores}")
        return redirect("achievements")
