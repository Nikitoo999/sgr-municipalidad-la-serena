"""Configuración del módulo de Atenciones (Parte 7).

El listado, la exportación y los formularios (crear/consultar/editar) se acotan
con :func:`attentions_scope`: superadmin según su delegación activa ("Todas" o
una), coordinador según su delegación activa, delegado su delegación fija y
funcionario únicamente donde él es responsable. Las vistas de crear/editar/ver
son propias para respetar el diseño "Ingreso de atención" (búsqueda de
solicitante, delegación fija por perfil, tipo/sub atención dependientes,
descripción con contador, estado editable solo al editar).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views import View

from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook

from operaciones.models import Attention, Neighbor

from ..access import (
    ALL_DELEGATIONS,
    ModulePermissionMixin,
    allowed_delegations,
    get_active_delegation,
    get_role,
)
from ..audit import audit
from .config import CELL_DELEGATION, CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import AttentionForm
from .search import apply_search
from .views import (
    BORDER,
    HEADER_ALIGN,
    HEADER_FILL,
    HEADER_FONT,
    CrudBaseMixin,
    CrudCreateView,
    CrudDetailView,
    CrudListView,
    CrudUpdateView,
    filtered_queryset,
)


def attentions_scope(request, queryset):
    """Atenciones visibles según rol + delegación activa.

    - Superadmin: todas, o solo las de su delegación activa.
    - Coordinador: su delegación activa (entre las autorizadas).
    - Delegado: su delegación fija.
    - Funcionario: solo las que él ingresó (responsable = usuario).
    """
    role = get_role(request.user)
    if role is None:
        return queryset.none()
    active = get_active_delegation(request)
    if active is not None and active != ALL_DELEGATIONS:
        queryset = queryset.filter(delegation_id=active.pk)
    if role.scope == "own_records":
        queryset = queryset.filter(responsible_id=request.user.pk)
    return queryset


def _deleg_label(delegation):
    return f"{delegation.code} | Delegación {delegation.name}"


def scope_note(request):
    """Aviso de alcance sobre la tabla (textos del diseño ``bannerFor``)."""
    role = get_role(request.user)
    if role is None:
        return ""
    active = get_active_delegation(request)
    if role.scope == "own_records":
        return "Tu perfil muestra solo las atenciones que ingresaste tú."
    if role.scope == "all":
        if active == ALL_DELEGATIONS:
            return "Vista global: todas las delegaciones."
        return (
            f"Filtrado por {_deleg_label(active)}. Cambia la delegación activa "
            "en la cabecera."
        )
    if role.scope == "authorized":
        count = len(allowed_delegations(request.user))
        return (
            f"Delegación activa: {_deleg_label(active)}. Puedes cambiarla en la "
            f"cabecera entre tus {count} delegaciones autorizadas."
        )
    return f"Tu perfil muestra solo registros de {_deleg_label(active)}."


ATTENTIONS_MODULE = ModuleConfig(
    module_key="attentions",
    slug="atenciones",
    model=Attention,
    form_class=AttentionForm,
    list_title="Atenciones",
    singular_label="Atención",
    columns=(
        ColumnSpec("number", "N°"),
        ColumnSpec("created_at_display", "Fecha y hora"),
        ColumnSpec("solicitante_name", "Solicitante"),
        ColumnSpec("type_name", "Tipo"),
        ColumnSpec("subtype_name", "Sub atención"),
        ColumnSpec("delegation", "Delegación", cell=CELL_DELEGATION),
        ColumnSpec("responsible_name", "Responsable"),
        ColumnSpec("status_display", "Estado", cell=CELL_STATUS),
    ),
    search_fields=(
        "number", "neighbor__full_name", "neighbor__identifier",
        "attention_type__name", "attention_subtype__name",
        "responsible__first_name", "responsible__last_name",
        "responsible__username", "delegation__name", "delegation__code",
    ),
    status_field="status",
    status_options=(
        ("received", "Ingresada"),
        ("in_progress", "En gestión"),
        ("resolved", "Resuelta"),
    ),
    ordering=("number",),
    scope=attentions_scope,
    form_template="portal/crud/attention_form.html",
)

register_module(ATTENTIONS_MODULE)


class _AttentionFormContext:
    """Contexto extra compartido por las vistas de formulario de atención."""

    def attention_form_context(self, form):
        editing = self.mode != "create"
        if editing and self.object is not None:
            responsible_name = self.object.responsible_name
            date_text = self.object.created_at_display
            neighbor_label = (
                f"{self.object.neighbor.identifier} | {self.object.neighbor.full_name}"
                if self.object.neighbor_id else ""
            )
        else:
            responsible_name = (
                self.request.user.get_full_name() or self.request.user.username
            )
            date_text = "automáticas"
            neighbor_label = ""
        subtype_type_map = {
            subtype.pk: subtype.attention_type_id
            for subtype in form.fields["attention_subtype"].queryset
        }
        # Delegación: select (coordinador/superadmin al crear) o texto fijo.
        fixed = form.fixed_delegation
        if editing and self.object is not None:
            fixed = self.object.delegation
        fixed_label = ""
        if fixed is not None:
            suffix = ""
            if not editing and "delegation" not in form.fields:
                suffix = "  [Asignada por perfil]"
            fixed_label = f"{fixed.code} | Delegación {fixed.name}{suffix}"
        return {
            "subtype_type_map": subtype_type_map,
            "responsible_name": responsible_name,
            "attention_date_text": date_text,
            "neighbor_label": neighbor_label,
            "fixed_delegation_label": fixed_label,
            "delegation_is_select": "delegation" in form.fields,
            "status_in_form": "status" in form.fields,
        }



class AttentionListView(CrudListView):
    """Listado de atenciones con aviso de alcance y botón "Ingresar atención"."""

    template_name = "portal/crud/attention_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["scope_note"] = scope_note(self.request)
        return context


class AttentionCreateView(_AttentionFormContext, CrudCreateView):
    """Ingreso de atención: responsable = usuario de sesión, N° automático."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.attention_form_context(context["form"]))
        return context

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.responsible = self.request.user
        obj.save()
        audit(
            self.request, "create", module="attentions",
            object_repr=str(obj), detail=f"Creado por {self.request.user}",
        )
        messages.success(
            self.request,
            f"Atención {obj.number} ingresada correctamente en "
            f"{obj.delegation.code} | Delegación {obj.delegation.name}. "
            "La fecha y la hora se asignaron automáticamente.",
        )
        return redirect(self.get_success_url())


class AttentionUpdateView(_AttentionFormContext, CrudUpdateView):
    """Edición: solo tipo, sub atención, descripción y estado."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.attention_form_context(context["form"]))
        return context

    def form_valid(self, form):
        obj = form.save()
        audit(
            self.request, "edit", module="attentions",
            object_repr=str(obj), detail=f"Editado por {self.request.user}",
        )
        messages.success(
            self.request,
            f"Cambios guardados. La atención {obj.number} se actualizó y el "
            "cambio quedó en la auditoría.",
        )
        return redirect(self.get_success_url())


class AttentionDetailView(_AttentionFormContext, CrudDetailView):
    """Consulta de una atención (solo lectura)."""

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.config.form_class(instance=self.object, request=request)
        for field in form.fields.values():
            field.widget.attrs["disabled"] = True
        return self.render_to_response(self.get_context_data(form=form))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.attention_form_context(context["form"]))
        return context



class AttentionExportView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Exporta a Excel las atenciones filtradas y con alcance."""

    action = "export"

    def get(self, request, *args, **kwargs):
        query = (request.GET.get("q") or "").strip()
        estado = request.GET.get("estado") or ""

        queryset = filtered_queryset(request, self.config)
        rows_all = list(apply_search(queryset, self.config.search_fields, query))

        headers = ["N°", "Fecha y hora", "Solicitante", "Tipo", "Sub atención",
                   "Delegación", "Responsable", "Estado"]

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Atenciones"

        for index, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=index, value=header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = HEADER_ALIGN
            cell.border = BORDER

        for row_index, obj in enumerate(rows_all, start=2):
            values = [
                obj.number,
                obj.created_at_display,
                obj.solicitante_name,
                obj.type_name,
                obj.subtype_name,
                obj.delegation_label,
                obj.responsible_name,
                obj.status_display,
            ]
            for col_index, value in enumerate(values, start=1):
                cell = sheet.cell(row=row_index, column=col_index, value=value)
                cell.border = BORDER

        for index, header in enumerate(headers, start=1):
            letter = get_column_letter(index)
            sheet.column_dimensions[letter].width = max(len(header) + 2, 14)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="atenciones.xlsx"'
        workbook.save(response)
        return response


class AttentionNeighborsView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Búsqueda JSON de solicitantes (máx. 10) para el ingreso de atención."""

    module = "attentions"
    action = "view"

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        results = []
        if query:
            neighbors = (
                Neighbor.alive.filter(full_name__icontains=query)
                | Neighbor.alive.filter(identifier__icontains=query)
            )
            for neighbor in neighbors.order_by("full_name")[:10]:
                results.append({
                    "pk": neighbor.pk,
                    "label": f"{neighbor.identifier} | {neighbor.full_name}",
                })
        return JsonResponse({"results": results})
