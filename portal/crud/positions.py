"""Cargos y metas (RF-003, RF-006, RF-007 / HU-04, HU-05, HU-25).

- Mantenedor de cargos según el descriptor de funciones (código, nombre,
  resumen, funciones, si se evalúa en la matriz y estado).
- Ítems, ponderadores y metas de cada cargo por período: la suma de
  ponderadores debe ser 100 % (RN-001), salvo excepción formal con motivo, que
  queda en la auditoría. La meta no puede ser negativa (meta 0 = ítem sin meta
  fija, como Emergencia). Un período cerrado no se modifica (RN-013).
- Copiar las metas del período anterior para empezar un trimestre nuevo sin
  perder la historia (HU-25).

Las metas por cargo son comunes a todas las delegaciones: modificarlas exige
el permiso de editar del módulo (superadministrador).
"""

from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView

from operaciones.calculos import periodo_vigente
from sgr_core.models import Period, Position, PositionItemGoal, ProjectItem

from ..access import ModulePermissionMixin, get_access
from ..audit import audit
from ..modules import MODULE_ICONS, MODULE_LABELS
from .config import CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import CrudModelForm

#: Filas nuevas que ofrece el formulario de metas.
FILAS_NUEVAS = 3


class PositionForm(CrudModelForm):
    """Cargo del descriptor de funciones."""

    full_width_fields = ("summary", "functions")

    class Meta:
        model = Position
        fields = ("code", "name", "summary", "functions", "is_evaluated", "status")
        labels = {
            "code": "Código", "name": "Nombre del cargo", "summary": "Resumen del cargo",
            "functions": "Descriptor de funciones", "is_evaluated": "Se evalúa en la matriz",
            "status": "Estado",
        }
        help_texts = {
            "code": "Ej.: CAR08. Único.",
            "functions": "Funciones según el descriptor de cargos de las delegaciones.",
            "is_evaluated": "Desmárcalo para cargos que no se miden (p. ej., Delegado).",
        }
        widgets = {
            "code": forms.TextInput(attrs={"class": "in", "maxlength": 8}),
            "name": forms.TextInput(attrs={"class": "in", "maxlength": 60}),
            "summary": forms.Textarea(attrs={"class": "in", "rows": 2}),
            "functions": forms.Textarea(attrs={"class": "in", "rows": 6}),
            "is_evaluated": forms.CheckboxInput(attrs={"class": "chk"}),
            "status": forms.Select(attrs={"class": "in"}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        dup = Position.objects.filter(code__iexact=code)
        if self.instance.pk:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise forms.ValidationError("Ya existe un cargo con ese código.")
        return code


def position_delete_guard(position, request=None):
    if position.employees.filter(deleted_at__isnull=True).exists():
        return f"No se puede eliminar {position.name}: tiene funcionarios asignados. Márcalo como Inactivo."
    if position.item_goals.exists():
        return f"No se puede eliminar {position.name}: tiene metas cargadas. Márcalo como Inactivo."
    return ""


POSITIONS_MODULE = ModuleConfig(
    module_key="positions",
    slug="cargos",
    model=Position,
    form_class=PositionForm,
    list_title="Cargos y metas",
    singular_label="Cargo",
    gender="m",
    columns=(
        ColumnSpec("code", "Código", sort_key="codigo", sort_fields=("code",)),
        ColumnSpec("name", "Nombre", sort_key="nombre", sort_fields=("name",)),
        ColumnSpec("evaluated_display", "Se evalúa", sort_key="evalua", sort_fields=("-is_evaluated", "code")),
        ColumnSpec("status", "Estado", cell=CELL_STATUS, sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("code", "name", "summary"),
    search_placeholder="Buscar por código o nombre del cargo...",
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    ordering=("code",),
    default_sort="codigo",
    delete_guard=position_delete_guard,
    form_template="portal/crud/position_form.html",
)

register_module(POSITIONS_MODULE)


def _decimal(value):
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return None


def periodo_anterior_con_metas(position, period):
    """Último período anterior a ``period`` con metas para el cargo."""
    return (
        Period.objects.filter(
            deleted_at__isnull=True, start_date__lt=period.start_date,
            position_goals__position=position, position_goals__deleted_at__isnull=True,
        ).distinct().order_by("-start_date").first()
    )


class PositionGoalsView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Ítems, ponderadores y metas de un cargo en un período."""

    template_name = "portal/position_goals.html"
    module = "positions"
    action = "view"

    def _setup(self):
        self.position = get_object_or_404(Position.alive, pk=self.kwargs["pk"])
        periodos = list(Period.objects.filter(deleted_at__isnull=True).order_by("-start_date"))
        pedido = self.request.GET.get("periodo") or self.request.POST.get("periodo") or ""
        self.period = next((p for p in periodos if str(p.pk) == pedido), None) or periodo_vigente()
        self.periodos = periodos

    def _goals(self):
        return list(
            PositionItemGoal.objects.filter(
                position=self.position, period=self.period, deleted_at__isnull=True,
            ).select_related("item").order_by("item__code")
        )

    def _can_edit(self):
        return get_access(self.request).can("positions", "edit")

    def get_context_data(self, **kwargs):
        if not hasattr(self, "position"):
            self._setup()
        context = super().get_context_data(**kwargs)
        goals = self._goals() if self.period else []
        presentes = {g.item_id for g in goals}
        suma = sum((g.weight for g in goals), Decimal("0"))
        anterior = periodo_anterior_con_metas(self.position, self.period) if self.period and not goals else None
        context.update({
            "active_module": "positions",
            "module_label": MODULE_LABELS["positions"],
            "module_icon": MODULE_ICONS["positions"],
            "position": self.position,
            "period": self.period,
            "periodos": self.periodos,
            "goals": goals,
            "suma": suma,
            "suma_ok": suma == 100,
            "items_disponibles": ProjectItem.alive.filter(status="Activo").exclude(pk__in=presentes).order_by("code"),
            "filas_nuevas": range(FILAS_NUEVAS),
            "cerrado": bool(self.period and self.period.status == "Cerrado"),
            "can_edit": self._can_edit(),
            "periodo_anterior": anterior,
        })
        return context

    def post(self, request, *args, **kwargs):
        self._setup()
        if not self._can_edit():
            messages.error(request, "No tienes permiso para modificar metas.")
            return redirect(self._url())
        if self.period is None or self.period.status == "Cerrado":
            messages.error(request, "El período está cerrado: sus metas no se modifican (RN-013).")
            return redirect(self._url())
        if request.POST.get("accion") == "copiar":
            return self._copy(request)
        return self._save(request)

    def _url(self):
        base = reverse("position_goals", args=[self.position.pk])
        return f"{base}?periodo={self.period.pk}" if self.period else base

    def _save(self, request):
        goals = self._goals()
        errores, filas = [], []
        for g in goals:
            if request.POST.get(f"delete_{g.pk}") == "1":
                continue
            peso, meta = _decimal(request.POST.get(f"weight_{g.pk}")), _decimal(request.POST.get(f"target_{g.pk}"))
            filas.append((g.item, peso, meta, g))
        presentes = {g.item_id for g in goals}
        for i in range(FILAS_NUEVAS):
            item_pk = request.POST.get(f"new_item_{i}") or ""
            if not item_pk:
                continue
            item = ProjectItem.alive.filter(pk=item_pk, status="Activo").first()
            if item is None or item.pk in presentes:
                errores.append("Hay un ítem nuevo repetido o no válido.")
                continue
            presentes.add(item.pk)
            filas.append((item, _decimal(request.POST.get(f"new_weight_{i}")),
                          _decimal(request.POST.get(f"new_target_{i}")), None))
        for item, peso, meta, _g in filas:
            if peso is None or not (Decimal("0") <= peso <= Decimal("100")):
                errores.append(f"{item.name}: el ponderador debe estar entre 0 y 100.")
            if meta is None or meta < 0:
                errores.append(f"{item.name}: la meta no puede ser negativa.")
        suma = sum((p for _i, p, _m, _g in filas if p is not None), Decimal("0"))
        motivo = " ".join((request.POST.get("motivo_excepcion") or "").split())[:300]
        excepcion = request.POST.get("excepcion") == "1"
        if not errores and suma != 100 and not (excepcion and len(motivo) >= 10):
            errores.append(
                f"Los ponderadores suman {suma} %: deben sumar 100 % (RN-001). Si es una excepción "
                "formal, márcala e indica el motivo."
            )
        if errores:
            for error in dict.fromkeys(errores):
                messages.error(request, error)
            return redirect(self._url())
        cambios = []
        with transaction.atomic():
            conservar = set()
            for item, peso, meta, goal in filas:
                if goal is None:
                    PositionItemGoal.objects.update_or_create(
                        position=self.position, item=item, period=self.period,
                        defaults={"weight": peso, "target_value": meta, "deleted_at": None},
                    )
                    cambios.append(f"+{item.code} {peso}%/{meta}")
                else:
                    if goal.weight != peso or goal.target_value != meta:
                        cambios.append(f"{item.code} {goal.weight}%/{goal.target_value} → {peso}%/{meta}")
                        goal.weight, goal.target_value = peso, meta
                        goal.save(update_fields=["weight", "target_value", "updated_at"])
                conservar.add(item.pk)
            for g in goals:
                if g.item_id not in conservar:
                    cambios.append(f"-{g.item.code}")
                    g.delete()
        detalle = "; ".join(cambios) or "sin cambios"
        if suma != 100:
            detalle += f" · EXCEPCIÓN suma {suma}%: {motivo}"
        audit(request, "edit", module="positions", object_repr=f"{self.position.name} · {self.period.name}",
              detail=detalle)
        messages.success(request, f"Metas de {self.position.name} guardadas para {self.period.name} (suma {suma} %).")
        return redirect(self._url())

    def _copy(self, request):
        if self._goals():
            messages.info(request, "El cargo ya tiene metas en este período.")
            return redirect(self._url())
        origen = periodo_anterior_con_metas(self.position, self.period)
        if origen is None:
            messages.error(request, "No hay un período anterior con metas para copiar.")
            return redirect(self._url())
        copiadas = 0
        with transaction.atomic():
            for g in PositionItemGoal.objects.filter(position=self.position, period=origen, deleted_at__isnull=True):
                PositionItemGoal.objects.update_or_create(
                    position=self.position, item=g.item, period=self.period,
                    defaults={"weight": g.weight, "target_value": g.target_value, "deleted_at": None},
                )
                copiadas += 1
        audit(request, "create", module="positions", object_repr=f"{self.position.name} · {self.period.name}",
              detail=f"{copiadas} metas copiadas desde {origen.name}")
        messages.success(request, f"Se copiaron {copiadas} metas desde {origen.name}. Revísalas y ajústalas si corresponde.")
        return redirect(self._url())
