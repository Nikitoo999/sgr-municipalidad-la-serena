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

Bloque 2A (mantenedores):

- Títulos y mensajes con el nombre propio de la entidad ("Nuevo usuario",
  "Editar delegación", "Ítem creado correctamente"), leídos de ``ModuleConfig``.
- Cada listado recuerda en ``request.session`` su último estado (búsqueda,
  estado, filtros propios, orden, filas por página y página). Al volver desde
  el menú o al refrescar sin parámetros se reutiliza; ``?limpiar=1`` lo borra.
- Orden por columna (``?orden=clave`` / ``?orden=-clave``) y filtros propios
  por tabla, ambos declarados en ``ModuleConfig`` y validados con listas
  blancas (un valor inválido se ignora, nunca da error 500).
- El Excel se descarga como ``<modulo>_<AAAAMMDD_HHMM>_<usuario>.xlsx``.
"""

import re
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

#: Clave de ``request.session`` con el último estado de cada listado:
#: ``{"delegations": {"q": "centro", "por_pagina": "15"}, ...}``.
LIST_STATE_SESSION_KEY = "sgr_list_state"
#: Parámetro que borra el estado guardado de la tabla (``?limpiar=1``).
CLEAR_PARAM = "limpiar"
#: Largo máximo que se guarda por parámetro (la sesión no es un depósito).
MAX_PARAM_LENGTH = 200

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def scoped_queryset(request, config):
    """Queryset vivo del módulo, con el orden y el alcance aplicados."""
    queryset = config.model.alive.all()
    if config.select_related:
        queryset = queryset.select_related(*config.select_related)
    if config.ordering:
        queryset = queryset.order_by(*config.ordering)
    if config.scope is not None:
        queryset = config.scope(request, queryset)
    return queryset


def apply_status_filter(queryset, config, estado):
    """Filtra por estado si el valor está entre las opciones del módulo."""
    valid = {option[0] for option in config.status_options}
    if not estado or estado not in valid:
        return queryset
    if config.status_filter is not None:
        return config.status_filter(queryset, estado)
    if config.status_field:
        return queryset.filter(**{config.status_field: estado})
    return queryset


def filtered_queryset(request, config, estado=None):
    """Queryset vivo + alcance + filtro de estado (sin búsqueda ni página).

    ``estado`` es el valor ya resuelto del listado; si no se indica, se lee de
    la URL (compatibilidad con la Parte 4).
    """
    queryset = scoped_queryset(request, config)
    if estado is None:
        estado = request.GET.get("estado", "")
    return apply_status_filter(queryset, config, estado)


def querystring(query, estado, extra=None):
    """URL query conservando búsqueda y filtros (compatibilidad Parte 4)."""
    params = {}
    if query:
        params["q"] = query
    if estado:
        params["estado"] = estado
    if extra:
        params.update({key: value for key, value in extra.items() if value})
    return f"?{urlencode(params)}" if params else ""


# ---------------------------------------------------------------------------
# Estado del listado guardado en la sesión
# ---------------------------------------------------------------------------


def base_list_keys(config):
    """Parámetros GET que forman el estado de un listado del motor."""
    return (
        "q", "estado",
        *(spec.param for spec in config.filters),
        "orden", "por_pagina", "page",
    )


def remember_list_state(request, module_key, keys):
    """Parámetros efectivos del listado: los de la URL o los guardados.

    - Si la URL trae cualquiera de ``keys`` (aunque venga vacío, como al
      borrar la búsqueda), esos valores mandan y se guardan en
      ``request.session`` como el último estado usado en esta tabla.
    - Si no trae ninguno (volver desde el menú, refrescar, volver después de
      guardar), se reutiliza el último estado guardado.

    Devuelve un ``dict`` con los valores no vacíos (sin validar: la vista los
    valida después igual que si vinieran en la URL).
    """
    store = request.session.get(LIST_STATE_SESSION_KEY)
    if not isinstance(store, dict):
        store = {}
    if any(key in request.GET for key in keys):
        state = {}
        for key in keys:
            value = (request.GET.get(key) or "").strip()[:MAX_PARAM_LENGTH]
            if value:
                state[key] = value
        if store.get(module_key) != state:
            if state:
                store[module_key] = state
            else:
                store.pop(module_key, None)
            request.session[LIST_STATE_SESSION_KEY] = store
        return state
    saved = store.get(module_key)
    return dict(saved) if isinstance(saved, dict) else {}


def forget_list_state(request, module_key):
    """Borra el estado guardado de una tabla (``?limpiar=1``)."""
    store = request.session.get(LIST_STATE_SESSION_KEY)
    if isinstance(store, dict) and module_key in store:
        store.pop(module_key)
        request.session[LIST_STATE_SESSION_KEY] = store


def build_querystring(params, keys, **overrides):
    """``?a=1&b=2`` con los parámetros vigentes (vacíos omitidos).

    ``overrides`` reemplaza valores; pasar ``None`` quita el parámetro.
    """
    data = {key: params.get(key, "") for key in keys}
    data.update(overrides)
    clean = {key: value for key, value in data.items() if value not in (None, "")}
    return f"?{urlencode(clean)}" if clean else ""


# ---------------------------------------------------------------------------
# Orden por columna, filtros propios y tamaño de página
# ---------------------------------------------------------------------------


def split_order(orden):
    """``"-fecha"`` -> ``("fecha", True)``; solo se admite UN guion inicial."""
    orden = (orden or "").strip()
    if orden.startswith("-"):
        return orden[1:], True
    return orden, False


def _flip(field_name):
    return field_name[1:] if field_name.startswith("-") else f"-{field_name}"


def order_queryset(queryset, config, orden):
    """Ordena por una clave pública de columna (``-clave`` = descendente).

    Una clave desconocida usa ``config.default_sort``. Siempre se agrega ``pk``
    como desempate para que la paginación sea estable.
    """
    sorts = config.sort_map
    key, descending = split_order(orden)
    if key not in sorts:
        key, descending = split_order(config.default_sort)
    if key not in sorts:
        return queryset
    if config.sort_annotate is not None:
        queryset = config.sort_annotate(queryset, key)
    fields = [_flip(name) if descending else name for name in sorts[key]]
    fields.append("-pk" if descending else "pk")
    return queryset.order_by(*fields)


def valid_page_size(config, raw):
    """Filas por página si está entre las permitidas; si no, cadena vacía."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return ""
    return str(value) if value in config.page_size_options else ""


def resolve_filters(request, config, raw):
    """Valores válidos de los filtros propios y sus controles para la plantilla."""
    values, controls = {}, []
    for spec in config.filters:
        choices = [(str(value), str(label)) for value, label in spec.options(request)]
        valid = {value for value, _label in choices}
        value = str(raw.get(spec.param) or "").strip()
        if value not in valid:
            value = ""
        values[spec.param] = value
        controls.append({
            "param": spec.param,
            "label": spec.label,
            "empty_label": spec.empty_label,
            "options": [
                {"value": option, "label": label, "selected": option == value}
                for option, label in choices
            ],
        })
    return values, controls


def resolve_list(request, config, raw):
    """Valida los parámetros del listado/exportación de un mantenedor.

    Devuelve ``(params, controles_de_filtro)``. ``params`` solo contiene
    valores válidos: lo que no está en las listas blancas queda vacío.
    """
    raw = raw or {}
    valid_states = {value for value, _label in config.status_options}
    estado = str(raw.get("estado") or "").strip()
    params = {
        "q": str(raw.get("q") or "").strip(),
        "estado": estado if estado in valid_states else "",
    }
    filter_values, controls = resolve_filters(request, config, raw)
    params.update(filter_values)
    orden = str(raw.get("orden") or "").strip()
    params["orden"] = orden if split_order(orden)[0] in config.sort_map else ""
    params["por_pagina"] = valid_page_size(config, raw.get("por_pagina"))
    params["page"] = str(raw.get("page") or "").strip()
    return params, controls


def listing_queryset(request, config, params):
    """Alcance + estado + filtros propios + búsqueda + orden (en la BD)."""
    queryset = filtered_queryset(request, config, estado=params.get("estado", ""))
    for spec in config.filters:
        value = params.get(spec.param, "")
        if value:
            queryset = spec.filter_queryset(queryset, value)
    queryset = apply_search(queryset, config.search_fields, params.get("q", ""))
    return order_queryset(queryset, config, params.get("orden", ""))


def sort_headers(config, params, build_url):
    """Encabezados ordenables: un clic ordena ascendente y el siguiente invierte."""
    current_key, current_desc = split_order(params.get("orden") or config.default_sort)
    headers = []
    for column in config.columns:
        key = column.sort_key if column.sort_key in config.sort_map else ""
        is_current = bool(key) and key == current_key
        next_order = f"-{key}" if is_current and not current_desc else key
        headers.append({
            "label": column.header,
            "url": build_url(orden=next_order, page=None) if key else "",
            "sortable": bool(key),
            "current": is_current,
            "direction": ("desc" if current_desc else "asc") if is_current else "",
            "aria_sort": (
                "descending" if current_desc else "ascending"
            ) if is_current else "none",
        })
    return headers


def paginate_listing(config, queryset, params, keys):
    """Paginador + enlaces (con puntos suspensivos) + filas del listado."""
    page_size = int(params.get("por_pagina") or config.page_size_options[0])
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(params.get("page") or None)

    def url(**overrides):
        return build_querystring(params, keys, **overrides)

    page_links = []
    for number in paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1):
        if number == Paginator.ELLIPSIS:
            page_links.append({"ellipsis": True})
        else:
            page_links.append({
                "number": number,
                "url": url(page=number),
                "current": number == page_obj.number,
            })

    rows = [
        {
            "pk": obj.pk,
            "label": config.label_for(obj),
            "cells": [resolve_cell(obj, column) for column in config.columns],
        }
        for obj in page_obj.object_list
    ]
    return {
        "rows": rows,
        "page_obj": page_obj,
        "page_links": page_links,
        "prev_url": url(page=page_obj.previous_page_number() if page_obj.has_previous() else None),
        "next_url": url(page=page_obj.next_page_number() if page_obj.has_next() else None),
        "showing_from": page_obj.start_index(),
        "showing_to": page_obj.end_index(),
        "total": paginator.count,
        "page_size": page_size,
        "page_size_options": config.page_size_options,
        "headers": sort_headers(config, params, url),
        "current_order": params.get("orden", ""),
    }


def export_filename(slug, user):
    """Nombre del Excel: ``<modulo>_<AAAAMMDD_HHMM>_<usuario>.xlsx``.

    La hora es la local (America/Santiago). Del usuario se usa el nombre de
    cuenta (si es un correo, solo la parte antes de la @) con caracteres
    seguros para un nombre de archivo.
    """
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
    username = ""
    if user is not None and getattr(user, "is_authenticated", False):
        username = user.get_username() or ""
    username = username.split("@", 1)[0]
    username = re.sub(r"[^A-Za-z0-9._-]+", "-", username).strip("-.") or "usuario"
    return f"{slug}_{stamp}_{username}.xlsx"


def xlsx_response(workbook, filename):
    """Respuesta HTTP de descarga para un libro de openpyxl."""
    response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


def _params_detail(params, keys):
    """Resumen de filtros para la auditoría (``q='x' estado='Activo'``)."""
    return " ".join(
        f"{key}={params.get(key, '')!r}" for key in keys if key not in ("page", "por_pagina")
    )


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
    """Listado con búsqueda, estado, filtros propios, orden y paginación.

    El último estado usado (filtros, orden, filas por página y página) se
    guarda en ``request.session`` por tabla; ``?limpiar=1`` lo borra.
    """

    template_name = "portal/crud/list.html"
    action = "view"
    #: Parámetros efectivos (URL o sesión) resueltos en ``get``.
    list_params = None

    def list_keys(self):
        return base_list_keys(self.config)

    def get(self, request, *args, **kwargs):
        if CLEAR_PARAM in request.GET:
            forget_list_state(request, self.config.module_key)
            return redirect(request.path)
        self.list_params = remember_list_state(
            request, self.config.module_key, self.list_keys(),
        )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.config
        request = self.request
        keys = self.list_keys()

        params, filter_controls = resolve_list(request, config, self.list_params or {})
        queryset = listing_queryset(request, config, params)
        context.update(paginate_listing(config, queryset, params, keys))

        filters_active = bool(params["q"] or params["estado"]) or any(
            params.get(spec.param) for spec in config.filters
        )
        list_url = reverse(config.module_key)
        context.update(
            {
                "active_module": config.module_key,
                "config": config,
                "columns": config.columns,
                "query": params["q"],
                "estado": params["estado"],
                "status_options": config.status_options,
                "filter_controls": filter_controls,
                "empty_kind": "results" if filters_active else "records",
                "search_url": list_url,
                "clear_url": f"{list_url}?{CLEAR_PARAM}=1",
                "export_url": reverse(f"{config.module_key}_export")
                + build_querystring(params, keys, page=None, por_pagina=None),
                "new_url": reverse(f"{config.module_key}_new"),
                "detail_url_name": f"{config.module_key}_detail",
                "edit_url_name": f"{config.module_key}_edit",
                "delete_url_name": f"{config.module_key}_delete",
                **self.access_flags(),
            }
        )
        return context


def _form_context(view, context):
    """Contexto común de crear/editar/consultar (títulos con nombre propio)."""
    config = view.config
    mode = view.mode
    form = context.get("form")
    code_preview = ""
    # Código automático: al crear se muestra el próximo correlativo (solo
    # referencial; el definitivo se asigna al guardar).
    if mode == "create" and hasattr(config.model, "next_code"):
        if form is None or "code" not in form.fields:
            code_preview = config.model.next_code()
    return {
        "active_module": config.module_key,
        "config": config,
        "mode": mode,
        "page_action": config.page_title(mode),
        "save_label": config.save_label if mode == "create" else "Guardar cambios",
        "code_preview": code_preview,
        "has_errors": bool(getattr(form, "errors", False)),
        "cancel_url": reverse(config.module_key),
        "is_create": mode == "create",
        "is_view": mode == "view",
        **view.access_flags(),
    }


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
        context.update(_form_context(self, context))
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
        message = self.config.success_message("create")
        code = getattr(obj, "code", "")
        if code:
            message = f"{message[:-1]} con el código {code}."
        messages.success(self.request, message)
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

    def get_template_names(self):
        """Plantilla del módulo (por defecto ``portal/crud/form.html``)."""
        if self.template_name != CrudUpdateView.template_name:
            return [self.template_name]
        return [self.config.form_template]

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
        messages.success(self.request, self.config.success_message("edit"))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_form_context(self, context))
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
        messages.success(request, self.config.success_message("delete"))
        return redirect(self.config.module_key)


class CrudExportView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Exporta a Excel TODAS las filas del resultado filtrado y con alcance.

    Lee los mismos parámetros que el listado (búsqueda, estado, filtros
    propios y orden), así el archivo coincide con lo que se ve en pantalla
    (menos la paginación).
    """

    action = "export"

    def get(self, request, *args, **kwargs):
        config = self.config
        params, _controls = resolve_list(request, config, request.GET)
        rows_all = list(listing_queryset(request, config, params))

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

        widths = [max(len(column.header) + 2, 14) for column in columns]
        for row_index, obj in enumerate(rows_all, start=2):
            for col_index, column in enumerate(columns, start=1):
                value = _export_value(obj, column)
                cell = sheet.cell(row=row_index, column=col_index, value=value)
                cell.border = BORDER
                widths[col_index - 1] = max(widths[col_index - 1], len(value))

        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = min(width, 48)
        sheet.freeze_panes = "A2"

        filename = export_filename(config.slug, request.user)
        audit(
            request, "export", module=config.module_key,
            object_repr=f"{len(rows_all)} registros",
            detail=f"{filename} · {_params_detail(params, base_list_keys(config))}",
        )
        return xlsx_response(workbook, filename)
