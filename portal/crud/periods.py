"""Períodos de medición (RF-005 / HU-28) y cierre de trimestre con traspaso.

- Mantenedor: nombre, inicio y término; el trimestre se calcula desde el
  inicio y la lista muestra los días computables (hábiles). La fecha de
  término no puede ser anterior al inicio y los períodos no se superponen.
- Un período cerrado no se edita ni se borra (RN-013): primero se reabre, con
  motivo y auditoría.
- Cierre de trimestre: los pendientes (tubo y atenciones) pasan al trimestre
  siguiente con PRIORIDAD y aviso (``operaciones.periodos``).

Los períodos son globales: crearlos, cerrarlos o reabrirlos exige alcance
"Todas las delegaciones" (superadministrador). Coordinadores y delegados los
consultan y ven los pendientes de su alcance.
"""

from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from operaciones import periodos as reglas_periodo
from operaciones.calculos import periodo_vigente
from sgr_core.models import Period

from ..access import ModulePermissionMixin, allowed_delegations, get_access, get_role
from ..audit import audit
from ..modules import MODULE_ICONS, MODULE_LABELS
from .config import CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import CrudModelForm


class PeriodForm(CrudModelForm):
    """Período de medición: nombre, inicio y término (el trimestre se calcula)."""

    class Meta:
        model = Period
        fields = ("name", "start_date", "end_date")
        labels = {
            "name": "Nombre del período",
            "start_date": "Fecha de inicio",
            "end_date": "Fecha de término",
        }
        help_texts = {
            "name": "Ej.: Trimestre Ene-Mar 2027.",
            "end_date": "Los días computables (hábiles) se calculan con estas fechas.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "in", "maxlength": 30}),
            "start_date": forms.DateInput(attrs={"class": "in", "type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"class": "in", "type": "date"}, format="%Y-%m-%d"),
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.status == "Cerrado":
            raise forms.ValidationError(
                "El período está cerrado: para modificarlo, primero reábrelo desde «Cierre de trimestre»."
            )
        inicio, fin = cleaned.get("start_date"), cleaned.get("end_date")
        if inicio and fin:
            if fin < inicio:
                self.add_error("end_date", "La fecha de término no puede ser anterior al inicio.")
            else:
                cruce = Period.objects.filter(
                    deleted_at__isnull=True, start_date__lte=fin, end_date__gte=inicio,
                )
                if self.instance.pk:
                    cruce = cruce.exclude(pk=self.instance.pk)
                otro = cruce.first()
                if otro is not None:
                    self.add_error("start_date", f"Se superpone con «{otro.name}».")
        return cleaned

    def save(self, commit=True):
        period = super().save(commit=False)
        period.quarter = (period.start_date.month - 1) // 3 + 1
        if not period.pk:
            period.status = "En curso"
        if commit:
            period.save()
        return period


def period_delete_guard(period, request=None):
    if period.status == "Cerrado":
        return "Un período cerrado no se elimina (RN-013)."
    if period.position_goals.filter(deleted_at__isnull=True).exists() or period.goals.exists():
        return (
            f"No se puede eliminar «{period.name}» porque tiene metas asociadas. "
            "Elimina primero sus metas o conserva el período."
        )
    return ""


PERIODS_MODULE = ModuleConfig(
    module_key="periods",
    slug="periodos",
    model=Period,
    form_class=PeriodForm,
    list_title="Períodos de medición",
    singular_label="Período",
    gender="m",
    columns=(
        ColumnSpec("name", "Nombre", sort_key="nombre", sort_fields=("name",)),
        ColumnSpec("start_display", "Inicio", sort_key="inicio", sort_fields=("start_date",)),
        ColumnSpec("end_display", "Término", sort_key="termino", sort_fields=("end_date",)),
        ColumnSpec("quarter_display", "Trimestre", sort_key="trimestre", sort_fields=("quarter", "start_date")),
        ColumnSpec("business_days", "Días computables"),
        ColumnSpec("status", "Estado", cell=CELL_STATUS, sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("name",),
    search_placeholder="Buscar por nombre del período...",
    status_field="status",
    status_options=(("En curso", "En curso"), ("Cerrado", "Cerrado")),
    ordering=("-start_date",),
    default_sort="-inicio",
    delete_guard=period_delete_guard,
    toolbar_links=(("Cierre de trimestre", "period_close"),),
)

register_module(PERIODS_MODULE)


def _scope_delegation_ids(request):
    """Delegaciones cuyos pendientes ve el usuario (None = todas)."""
    role = get_role(request.user)
    if role is not None and role.scope == "all":
        return None
    return [d.pk for d in allowed_delegations(request.user)]


class PeriodCloseView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Cierre de trimestre y traspaso con prioridad (y reapertura auditada)."""

    template_name = "portal/period_close.html"
    module = "periods"
    action = "view"

    def _can_manage(self):
        role = get_role(self.request.user)
        return (
            role is not None and role.scope == "all"
            and get_access(self.request).can("periods", "edit")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        abiertos = list(Period.objects.filter(deleted_at__isnull=True, status="En curso").order_by("start_date"))
        cerrados = list(Period.objects.filter(deleted_at__isnull=True, status="Cerrado").order_by("-start_date")[:6])
        pedido = self.request.GET.get("periodo", "")
        seleccionado = next((p for p in abiertos if str(p.pk) == pedido), None)
        if seleccionado is None:
            vencidos = [p for p in abiertos if p.end_date < hoy]
            seleccionado = vencidos[0] if vencidos else (periodo_vigente(hoy) if abiertos else None)
            if seleccionado is not None and seleccionado.status != "En curso":
                seleccionado = abiertos[0] if abiertos else None
        destinos, siguiente_nuevo = [], ""
        tubos = atenciones = []
        if seleccionado is not None:
            destinos = list(Period.objects.filter(
                deleted_at__isnull=True, status="En curso", start_date__gt=seleccionado.end_date,
            ).order_by("start_date"))
            if not destinos:
                inicio, _fin, _q = reglas_periodo.fechas_trimestre(seleccionado.end_date + timedelta(days=1))
                siguiente_nuevo = reglas_periodo.nombre_trimestre(inicio)
            t_qs, a_qs = reglas_periodo.pendientes(seleccionado, _scope_delegation_ids(self.request))
            tubos = list(t_qs.select_related("delegation", "responsible__user").order_by("delegation__code", "request_date")[:200])
            atenciones = list(a_qs.select_related("delegation", "neighbor").order_by("delegation__code", "created_at")[:200])
        context.update({
            "active_module": "periods",
            "module_label": MODULE_LABELS["periods"],
            "module_icon": MODULE_ICONS["periods"],
            "abiertos": abiertos,
            "cerrados": cerrados,
            "seleccionado": seleccionado,
            "termino_vencido": bool(seleccionado and seleccionado.end_date < hoy),
            "destinos": destinos,
            "siguiente_nuevo": siguiente_nuevo,
            "tubos": tubos,
            "atenciones": atenciones,
            "can_manage": self._can_manage(),
            "is_all_scope": _scope_delegation_ids(self.request) is None,
        })
        return context

    def post(self, request, *args, **kwargs):
        if not self._can_manage():
            raise PermissionDenied
        accion = request.POST.get("accion")
        if accion == "reabrir":
            return self._reopen(request)
        return self._close(request)

    def _close(self, request):
        periodo = Period.objects.filter(
            pk=request.POST.get("periodo") or 0, deleted_at__isnull=True, status="En curso",
        ).first()
        if periodo is None:
            messages.error(request, "Elige un período abierto para cerrar.")
            return redirect("period_close")
        if request.POST.get("confirmar") != "1":
            messages.error(request, "Confirma que revisaste los pendientes antes de cerrar.")
            return redirect(f"{request.path}?periodo={periodo.pk}")
        destino_pk = request.POST.get("destino", "")
        if destino_pk == "nuevo" or not destino_pk:
            destino = reglas_periodo.periodo_siguiente(periodo) or reglas_periodo.crear_siguiente(periodo)
        else:
            destino = Period.objects.filter(pk=destino_pk, deleted_at__isnull=True, status="En curso").first()
            if destino is None:
                messages.error(request, "El período de destino no es válido.")
                return redirect(f"{request.path}?periodo={periodo.pk}")
        try:
            resultado = reglas_periodo.cerrar_trimestre(periodo, destino, request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("period_close")
        audit(
            request, "close_period", module="periods", object_repr=periodo.name,
            detail=(f"Cerrado; destino {destino.name}; {resultado['tubos']} tubos y "
                    f"{resultado['atenciones']} atenciones traspasados con prioridad"),
        )
        messages.success(
            request,
            f"{periodo.name} cerrado. Pasaron a {destino.name} con prioridad: "
            f"{resultado['tubos']} solicitudes del tubo y {resultado['atenciones']} atenciones. "
            f"Se generaron {resultado['avisos']} aviso(s).",
        )
        return redirect("period_close")

    def _reopen(self, request):
        periodo = Period.objects.filter(
            pk=request.POST.get("periodo") or 0, deleted_at__isnull=True, status="Cerrado",
        ).first()
        motivo = " ".join((request.POST.get("motivo") or "").split())[:300]
        if periodo is None:
            messages.error(request, "Elige un período cerrado.")
        elif len(motivo) < 10:
            messages.error(request, "Indica el motivo de la reapertura (al menos 10 caracteres).")
        else:
            reglas_periodo.reabrir(periodo)
            audit(request, "reopen_period", module="periods", object_repr=periodo.name,
                  detail=f"Reabierto: {motivo}")
            messages.success(request, f"{periodo.name} quedó reabierto. La reapertura quedó en la auditoría.")
        return redirect("period_close")

