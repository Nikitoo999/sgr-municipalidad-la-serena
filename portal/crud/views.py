"""Vistas base del motor CRUD (Parte 4).

Todas las vistas de mantenedor (lista, crear, ver, editar, eliminar, exportar)
viven aquí y se configuran solo con ``module_key`` + la acción de permiso.
Reglas comunes:

- Toda autorización se valida en el servidor (``ModulePermissionMixin`` +
  alcance del queryset): ocultar botones no cuenta.
- El queryset excluye registros con borrado lógico (``deleted_at`` no nulo) vía
  el manager ``alive`` del modelo.
- Objeto existente pero fuera de alcance: 403 + AuditLog. Inexistente: 404.
- Las acciones que modifican datos van solo por POST (CSRF incluido).
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.edit import FormView

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook

from ..access import ModulePermissionMixin, get_access
from ..audit import audit
from ..context_processors import badge_colors
from .config import CELL_DELEGATION, CELL_STATUS, ModuleConfig, get_module
from .search import apply_search

#: Encabezado del Excel con el color institucional.
HEADER_FILL = PatternFill("solid", fgColor="920000")
HEADER_FONT = Font(color="FFFFFF", bold=True)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

#: Tamaños de página permitidos en los listados genéricos del motor.
PER_PAGE_OPTIONS = (5, 15, 30)
DEFAULT_PER_PAGE = 5
#: Orden por defecto: creación más reciente con ``pk`` descendente de desempate.
DEFAULT_ORDERING = ("-created_at", "-pk")


def _display(value):
    """Texto de una celda para listado/Excel (nunca datos sensibles)."""
    if value is None or value == "":
        return "—"
    return str(value)


def _export_value(obj, column):
    """Valor plano de una columna para el Excel (nunca datos sensibles)."""
    value = getattr(obj, column.field_name, None)
    if hasattr(value, "all"):  # relación (manager/queryset)
        value = list(value.all())
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            code = getattr(item, "code", "")
            name = getattr(item, "name", "")
            if code and name:
                parts.append(f"{code} · {name}")
            else:
                parts.append(str(item))
        value = ", ".join(parts)
    elif callable(value):
        value = value()
    return _display(value)


def _delegation_chips(value):
    """Normaliza una delegación, un conjunto o una lista a objetos."""
    if value is None:
        return []
    if hasattr(value, "all"):  # manager / queryset (varios chips)
        return list(value.all())
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def resolve_cell(obj, column):
    """Valor listo para la plantilla de una celda del listado."""
    value = getattr(obj, column.field_name, None)
    if column.cell == CELL_STATUS:
        return {"kind": "status", "text": str(value or "")}
    if column.cell == CELL_DELEGATION:
        chips = []
        for delegation in _delegation_chips(value):
            dc, dm = badge_colors(delegation.color)
            chips.append(
                {
                    "code": delegation.code,
                    "name": delegation.name,
                    "color": delegation.color or "",
                    "dc": dc,
                    "dm": dm,
                }
            )
        return {"kind": "delegation", "chips": chips}
    return {"kind": "text", "text": _display(value)}


def resolve_object_or_deny(request, config, queryset, pk):
    """Objeto del queryset acotado, con 403/404 según el caso.

    - Existe en el modelo vivo pero fuera del alcance -> 403 (+ auditoría).
    - No existe -> 404.
    """
    try:
        obj = queryset.filter(pk=pk).first()
    except (ValueError, TypeError):
        raise Http404("Registro inexistente.")
    if obj is not None:
        return obj
    if config.model.alive.filter(pk=pk).exists():
        audit(
            request, "access_denied", module=config.module_key,
            object_repr=str(pk),
            detail=f"{request.method} {request.path} (pk={pk} fuera de alcance)",
        )
        raise PermissionDenied
    raise Http404("Registro inexistente.")


def scoped_queryset(request, config, ordering=None):
    """Queryset vivo del módulo, con el orden y el alcance aplicados.

    ``ordering`` permite a los listados sobrescribir el orden declarado en el
    módulo (p. ej. orden dinámico por columna) sin tocar el queryset original.
    """
    queryset = config.model.alive.all()
    effective = ordering if ordering is not None else config.ordering
    if effective:
        queryset = queryset.order_by(*effective)
    if config.scope is not None:
        queryset = config.scope(request, queryset)
    return queryset


def filtered_queryset(request, config, ordering=None):
    """Queryset vivo + alcance + filtro de estado (sin búsqueda ni página)."""
    queryset = scoped_queryset(request, config, ordering=ordering)
    estado = request.GET.get("estado", "")
    valid = [option[0] for option in config.status_options]
    if config.status_field and estado in valid:
        queryset = queryset.filter(**{config.status_field: estado})
    return queryset


def _coerce_per_page(raw, fallback=DEFAULT_PER_PAGE):
    """Tamaño de página válido (5, 15 o 30); cualquier otro valor -> fallback."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value in PER_PAGE_OPTIONS else fallback


def _orderable_fields(config):
    """Campos del modelo ordenables en BD (columnas con campo real + fechas)."""
    fields = {"created_at", "pk", "id"}
    for column in config.columns:
        name = column.field_name
        try:
            config.model._meta.get_field(name)
        except Exception:
            continue
        fields.add(name)
    return fields


def _ordering_from(config, order, direction):
    """Orden dinámico validado; si no aplica, devuelve el orden por defecto."""
    if order in _orderable_fields(config):
        if direction == "desc":
            return (f"-{order}", "-pk")
        return (order, "-pk")
    return DEFAULT_ORDERING


def _list_params(query, estado, per_page, order, direction):
    """Parámetros GET que se conservan entre búsqueda, filtros y paginación."""
    params = {}
    if query:
        params["q"] = query
    if estado:
        params["estado"] = estado
    if per_page != DEFAULT_PER_PAGE:
        params["per_page"] = per_page
    if order:
        params["order"] = order
    if direction == "desc":
        params["direction"] = direction
    return params


def _list_url(query, estado, per_page, order, direction, page=None):
    """URL de listado conservando estado; ``page`` None omite la página."""
    params = _list_params(query, estado, per_page, order, direction)
    if page not in (None, ""):
        params["page"] = page
    return f"?{urlencode(params)}" if params else ""


#: Textos del modo del formulario (migas y título).
_PAGE_ACTIONS = {
    "create": "Crear registro",
    "edit": "Editar registro",
    "view": "Consulta de registro",
}


class CrudBaseMixin:
    """Resuelve la configuración del módulo y expone los permisos.

    ``setup`` corre antes de los ``dispatch`` de login y de permisos, así
    ``self.module`` ya existe cuando ``ModulePermissionMixin`` valida el
    permiso del módulo/acción.
    """

    module_key = None
    action = "view"
    config = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.config = get_module(self.module_key)
        self.module = self.config.module_key

    def access_flags(self):
        """Permisos de acción del usuario sobre este módulo (para el template)."""
        info = get_access(self.request)
        return {
            "can_view": info.can(self.module, "view"),
            "can_create": info.can(self.module, "create"),
            "can_edit": info.can(self.module, "edit"),
            "can_delete": info.can(self.module, "delete"),
            "can_export": info.can(self.module, "export"),
        }



class CrudListView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, TemplateView):
    """Listado con búsqueda, filtro, orden por columna y paginación variable.

    El estado del listado (búsqueda, filtro, tamaño, orden y página) se conserva
    en la sesión por módulo: al navegar fuera y volver se restaura lo último; si
    el usuario cambia la búsqueda, un filtro o el orden, la paginación se reinicia
    a la página 1.
    """

    template_name = "portal/crud/list.html"
    action = "view"

    def _state_key(self):
        return f"crud_state_{self.module_key}"

    def _resolve_state(self, request):
        """Estado del listado: el GET manda; si falta, se restaura de la sesión.

        Cambiar ``q``, ``estado`` o el tamaño de página reinicia a la página 1.
        ``?clear=1`` limpia búsqueda y filtros conservando tamaño y orden.
        """
        config = self.config
        saved = request.session.get(self._state_key(), {})

        if "clear" in request.GET:
            state = {
                "q": "",
                "estado": "",
                "per_page": _coerce_per_page(
                    request.GET.get("per_page"), saved.get("per_page", DEFAULT_PER_PAGE)
                ),
                "order": saved.get("order", ""),
                "direction": saved.get("direction", "asc"),
                "page": 1,
            }
            request.session[self._state_key()] = state
            request.session.modified = True
            return state

        per_page = _coerce_per_page(
            request.GET.get("per_page"), saved.get("per_page", DEFAULT_PER_PAGE)
        )
        per_page_changed = (
            "per_page" in request.GET
            and per_page != saved.get("per_page", DEFAULT_PER_PAGE)
        )

        filters_changed = False
        if "q" in request.GET:
            query = (request.GET.get("q") or "").strip()
            filters_changed = query != saved.get("q", "")
        else:
            query = saved.get("q", "")

        if "estado" in request.GET:
            estado = request.GET.get("estado") or ""
            if estado != saved.get("estado", ""):
                filters_changed = True
        else:
            estado = saved.get("estado", "")

        orderable = _orderable_fields(config)
        sort_changed = "order" in request.GET
        if "order" in request.GET:
            order = request.GET.get("order") or ""
            direction = request.GET.get("direction") or "asc"
            if direction not in ("asc", "desc"):
                direction = "asc"
            if order not in orderable:
                order = ""
        else:
            order = saved.get("order", "")
            direction = saved.get("direction", "asc")
            if order not in orderable:
                order = ""

        if "page" in request.GET:
            try:
                page = int(request.GET.get("page"))
            except (TypeError, ValueError):
                page = 1
            if page < 1:
                page = 1
        elif filters_changed or sort_changed or per_page_changed:
            page = 1
        else:
            page = saved.get("page", 1)

        state = {
            "q": query,
            "estado": estado,
            "per_page": per_page,
            "order": order,
            "direction": direction,
            "page": page,
        }
        request.session[self._state_key()] = state
        request.session.modified = True
        return state

    def _sortable_columns(self, config, state):
        """Columnas como dicts (header, sortable, url, active, arrow)."""
        orderable = _orderable_fields(config)
        columns = []
        for column in config.columns:
            entry = {
                "header": column.header,
                "sortable": False,
                "url": "",
                "active": False,
                "arrow": "",
            }
            if column.field_name in orderable:
                entry["sortable"] = True
                entry["active"] = state["order"] == column.field_name
                if entry["active"]:
                    new_direction = "asc" if state["direction"] == "desc" else "desc"
                    entry["arrow"] = "↑" if state["direction"] == "asc" else "↓"
                else:
                    new_direction = "asc"
                entry["url"] = _list_url(
                    state["q"], state["estado"], state["per_page"],
                    column.field_name, new_direction,
                )
            columns.append(entry)
        return columns

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.config
        request = self.request
        state = self._resolve_state(request)

        ordering = _ordering_from(config, state["order"], state["direction"])
        queryset = filtered_queryset(request, config, ordering=ordering)
        rows_all = apply_search(queryset, config.search_fields, state["q"])

        paginator = Paginator(rows_all, state["per_page"])
        page_obj = paginator.get_page(state["page"])

        rows = [
            {
                "pk": obj.pk,
                "cells": [resolve_cell(obj, column) for column in config.columns],
            }
            for obj in page_obj.object_list
        ]

        page_links = [
            {
                "number": number,
                "url": _list_url(
                    state["q"], state["estado"], state["per_page"],
                    state["order"], state["direction"], page=number,
                ),
                "current": number == page_obj.number,
            }
            for number in range(1, paginator.num_pages + 1)
        ]

        context.update(
            {
                "active_module": config.module_key,
                "config": config,
                "rows": rows,
                "columns": self._sortable_columns(config, state),
                "page_obj": page_obj,
                "page_links": page_links,
                "prev_url": _list_url(
                    state["q"], state["estado"], state["per_page"],
                    state["order"], state["direction"],
                    page=(page_obj.previous_page_number() if page_obj.has_previous() else None),
                ),
                "next_url": _list_url(
                    state["q"], state["estado"], state["per_page"],
                    state["order"], state["direction"],
                    page=(page_obj.next_page_number() if page_obj.has_next() else None),
                ),
                "showing_from": page_obj.start_index(),
                "showing_to": page_obj.end_index(),
                "total": paginator.count,
                "query": state["q"],
                "estado": state["estado"],
                "per_page": state["per_page"],
                "per_page_options": PER_PAGE_OPTIONS,
                "order": state["order"],
                "direction": state["direction"],
                "status_options": config.status_options,
                "empty_kind": "results" if (state["q"] or state["estado"]) else "records",
                "search_url": reverse(config.module_key),
                "clear_url": f"{reverse(config.module_key)}?clear=1",
                "export_url": (
                    f"{reverse(f'{config.module_key}_export')}"
                    f"{_list_url(state['q'], state['estado'], state['per_page'], state['order'], state['direction'])}"
                ),
                "new_url": reverse(f"{config.module_key}_new"),
                "detail_url_name": f"{config.module_key}_detail",
                "edit_url_name": f"{config.module_key}_edit",
                "delete_url_name": f"{config.module_key}_delete",
                **self.access_flags(),
            }
        )
        return context



class CrudFormView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, FormView):
    """Base de crear/editar/consultar: formulario compartido."""

    template_name = "portal/crud/form.html"
    action = "create"
    mode = "create"
    object = None

    def get_template_names(self):
        """Plantilla del módulo (por defecto ``portal/crud/form.html``)."""
        return [self.config.form_template]

    def get_form_class(self):
        return self.config.form_class

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object is not None:
            kwargs["instance"] = self.object
        # El request permite al formulario resolver reglas que dependen del
        # operador (roles ofrecidos, delegaciones administrables).
        kwargs["request"] = self.request
        return kwargs

    def get_success_url(self):
        return reverse(self.config.module_key)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_module": self.config.module_key,
                "config": self.config,
                "mode": self.mode,
                "page_action": _PAGE_ACTIONS[self.mode],
                "has_errors": bool(getattr(context.get("form"), "errors", False)),
                "cancel_url": reverse(self.config.module_key),
                "is_create": self.mode == "create",
                "is_view": self.mode == "view",
                **self.access_flags(),
            }
        )
        return context


class CrudCreateView(CrudFormView):
    """Crear un registro (acción create, solo POST guarda)."""

    action = "create"
    mode = "create"

    def form_valid(self, form):
        obj = form.save()
        audit(
            self.request, "create", module=self.config.module_key,
            object_repr=str(obj), detail=f"Creado por {self.request.user}",
        )
        messages.success(
            self.request, f"{self.config.singular_label} creada correctamente."
        )
        return super().form_valid(form)


class CrudDetailView(CrudFormView):
    """Consultar un registro: formulario deshabilitado y botón Volver."""

    action = "view"
    mode = "view"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.config.form_class(instance=self.object)
        for field in form.fields.values():
            field.widget.attrs["disabled"] = True
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        # Consultar no modifica datos: solo GET (evita guardados por error).
        raise Http404("Registro inexistente.")

    def get_object(self):
        queryset = scoped_queryset(self.request, self.config)
        return resolve_object_or_deny(
            self.request, self.config, queryset, self.kwargs["pk"]
        )



class CrudUpdateView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, FormView):
    """Editar un registro (acción edit)."""

    template_name = "portal/crud/form.html"
    action = "edit"
    mode = "edit"
    object = None

    def get_form_class(self):
        return self.config.form_class

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.render_to_response(self.get_context_data(form=self.get_form()))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_object(self):
        queryset = scoped_queryset(self.request, self.config)
        return resolve_object_or_deny(
            self.request, self.config, queryset, self.kwargs["pk"]
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object
        # El formulario de Usuarios exige el operador (request) para resolver
        # roles y delegaciones administrables en el servidor.
        kwargs["request"] = self.request
        return kwargs

    def get_success_url(self):
        return reverse(self.config.module_key)

    def form_valid(self, form):
        obj = form.save()
        audit(
            self.request, "edit", module=self.config.module_key,
            object_repr=str(obj), detail=f"Editado por {self.request.user}",
        )
        messages.success(
            self.request, f"{self.config.singular_label} actualizada correctamente."
        )
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "active_module": self.config.module_key,
                "config": self.config,
                "mode": self.mode,
                "page_action": _PAGE_ACTIONS[self.mode],
                "has_errors": bool(getattr(context.get("form"), "errors", False)),
                "cancel_url": reverse(self.config.module_key),
                "is_create": False,
                "is_view": False,
                **self.access_flags(),
            }
        )
        return context


class CrudDeleteView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Eliminar solo por POST: regla del módulo o borrado lógico."""

    action = "delete"

    def get(self, request, *args, **kwargs):
        # Eliminar no es una pantalla: la confirmación vive en el listado.
        raise Http404("Registro inexistente.")

    def post(self, request, *args, **kwargs):
        queryset = scoped_queryset(request, self.config)
        obj = resolve_object_or_deny(
            request, self.config, queryset, self.kwargs["pk"]
        )

        if self.config.delete_guard is not None:
            reason = self.config.delete_guard(obj, request)
            if reason:
                audit(
                    request, "delete", module=self.config.module_key,
                    object_repr=str(obj), detail=f"Bloqueado: {reason}",
                )
                messages.error(request, reason)
                return redirect(self.config.module_key)

        obj.deleted_at = timezone.now()
        obj.save(update_fields=["deleted_at", "updated_at"])
        audit(
            request, "delete", module=self.config.module_key,
            object_repr=str(obj), detail=f"Eliminado por {request.user}",
        )
        messages.success(
            request, f"{self.config.singular_label} eliminada correctamente."
        )
        return redirect(self.config.module_key)



class CrudExportView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Exporta a Excel TODAS las filas del resultado filtrado y con alcance."""

    action = "export"

    def get(self, request, *args, **kwargs):
        config = self.config
        query = (request.GET.get("q") or "").strip()
        estado = request.GET.get("estado") or ""

        queryset = filtered_queryset(request, config)
        rows_all = list(apply_search(queryset, config.search_fields, query))

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = config.list_title[:31]
        columns = config.export_columns

        for index, column in enumerate(columns, start=1):
            cell = sheet.cell(row=1, column=index, value=column.header)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = HEADER_ALIGN
            cell.border = BORDER

        for row_index, obj in enumerate(rows_all, start=2):
            for col_index, column in enumerate(columns, start=1):
                cell = sheet.cell(
                    row=row_index, column=col_index, value=_export_value(obj, column)
                )
                cell.border = BORDER

        for index, column in enumerate(columns, start=1):
            letter = get_column_letter(index)
            width = max(len(column.header) + 2, 14)
            for obj in rows_all:
                width = max(width, len(_export_value(obj, column)))
            sheet.column_dimensions[letter].width = min(width, 48)
        sheet.freeze_panes = "A2"

        filename = f"{config.slug}_{timezone.now():%Y%m%d}.xlsx"
        audit(
            request, "export", module=config.module_key,
            object_repr=f"{len(rows_all)} registros",
            detail=f"q={query!r} estado={estado!r}",
        )
        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        workbook.save(response)
        return response




