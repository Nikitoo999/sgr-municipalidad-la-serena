"""Configuración del módulo de Atenciones (Parte 7).

El listado, la exportación y los formularios (crear/consultar/editar) se acotan
con :func:`attentions_scope`: superadmin según su delegación activa ("Todas" o
una), coordinador según su delegación activa, delegado su delegación fija y
funcionario únicamente donde él es responsable. Las vistas de crear/editar/ver
son propias para respetar el diseño "Ingreso de atención" (búsqueda de
solicitante, delegación fija por perfil, tipo/sub atención dependientes,
descripción con contador, estado editable solo al editar).

Bloque 2A: el listado recuerda en ``request.session`` sus filtros, orden y
filas por página (``?limpiar=1`` los borra), el orden por columna usa el motor
común (``portal.crud.views.order_queryset``) y el Excel se descarga como
``atenciones_<AAAAMMDD_HHMM>_<usuario>.xlsx``.
"""

from datetime import date, datetime, time, timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Case, IntegerField, Value, When
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from openpyxl.utils import get_column_letter
from openpyxl.workbook import Workbook

from operaciones.models import Attention, Neighbor
from sgr_core.models import AttentionSubtype, AttentionType

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
    CLEAR_PARAM,
    HEADER_ALIGN,
    HEADER_FILL,
    HEADER_FONT,
    CrudBaseMixin,
    CrudCreateView,
    CrudDetailView,
    CrudListView,
    CrudUpdateView,
    build_querystring,
    export_filename,
    filtered_queryset,
    order_queryset,
    paginate_listing,
    scoped_queryset,
    split_order,
    xlsx_response,
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


#: Orden lógico del avance de una atención (Ingresada -> En gestión -> Resuelta).
_STATUS_PROGRESS = (
    Attention.AttentionStatus.RECEIVED,
    Attention.AttentionStatus.IN_PROGRESS,
    Attention.AttentionStatus.RESOLVED,
)


def attention_sort_annotate(queryset, key):
    """El estado se ordena por avance (no alfabético) con una anotación."""
    if key != "estado":
        return queryset
    return queryset.annotate(
        _estado_orden=Case(
            *[When(status=value, then=Value(position))
              for position, value in enumerate(_STATUS_PROGRESS)],
            default=Value(len(_STATUS_PROGRESS)),
            output_field=IntegerField(),
        )
    )


#: Tamaños de página permitidos (el primero es el valor por defecto).
PAGE_SIZE_OPTIONS = (5, 10, 25, 50)
DEFAULT_PAGE_SIZE = PAGE_SIZE_OPTIONS[0]
DEFAULT_SORT = "numero"


ATTENTIONS_MODULE = ModuleConfig(
    module_key="attentions",
    slug="atenciones",
    model=Attention,
    form_class=AttentionForm,
    list_title="Atenciones",
    singular_label="Atención",
    gender="f",
    columns=(
        ColumnSpec("number", "N°", sort_key="numero", sort_fields=("number",)),
        ColumnSpec("created_at_display", "Fecha y hora",
                   sort_key="fecha", sort_fields=("created_at",)),
        ColumnSpec("solicitante_name", "Solicitante",
                   sort_key="solicitante", sort_fields=("neighbor__full_name",)),
        ColumnSpec("type_name", "Tipo", sort_key="tipo", sort_fields=("attention_type__name",)),
        ColumnSpec("subtype_name", "Sub atención",
                   sort_key="subtipo", sort_fields=("attention_subtype__name",)),
        ColumnSpec("delegation", "Delegación", cell=CELL_DELEGATION,
                   sort_key="delegacion", sort_fields=("delegation__code",)),
        ColumnSpec("responsible_name", "Responsable", sort_key="responsable", sort_fields=(
            "responsible__first_name", "responsible__last_name", "responsible__username",
        )),
        ColumnSpec("status_display", "Estado", cell=CELL_STATUS,
                   sort_key="estado", sort_fields=("_estado_orden",)),
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
    default_sort=DEFAULT_SORT,
    sort_annotate=attention_sort_annotate,
    page_size_options=PAGE_SIZE_OPTIONS,
    select_related=(
        "neighbor", "attention_type", "attention_subtype", "delegation", "responsible",
    ),
    row_label=lambda attention: attention.number or f"N° {attention.pk}",
    scope=attentions_scope,
    form_template="portal/crud/attention_form.html",
)

register_module(ATTENTIONS_MODULE)


# ---------------------------------------------------------------------------
# Listado avanzado (filtros, orden y tamaño de página)
# ---------------------------------------------------------------------------
#
# Los mismos parámetros GET alimentan el listado y la exportación a Excel, así
# el archivo descargado siempre coincide con lo que se ve en pantalla (menos la
# paginación). Todo valor que llega por la URL se valida contra una lista
# blanca o se convierte a número/fecha; un valor inválido se ignora y nunca
# produce un error 500. El alcance por rol (``attentions_scope``) se aplica
# antes que cualquier filtro, así ningún parámetro puede ampliar lo visible.
# El último estado usado se guarda en ``request.session`` (ver
# ``CrudListView.get``): al volver al listado sin parámetros se reutiliza.

#: Clave pública de orden -> campos reales de la base de datos (derivado de
#: las columnas; la clave ``estado`` ordena por avance con una anotación).
SORT_FIELDS = ATTENTIONS_MODULE.sort_map

#: Campo de cada columna del listado -> clave de orden.
COLUMN_SORT_KEY = {
    column.field_name: column.sort_key
    for column in ATTENTIONS_MODULE.columns
    if column.sort_key
}

#: Parámetros GET que se conservan al paginar, ordenar y exportar.
LIST_PARAM_KEYS = (
    "q", "estado", "tipo", "subtipo", "delegacion", "responsable",
    "desde", "hasta", "orden", "por_pagina",
)

#: Parámetros que forman el estado guardado del listado (incluye la página).
LIST_STATE_KEYS = LIST_PARAM_KEYS + ("page",)

#: Parámetros que cuentan como "hay filtros activos".
FILTER_KEYS = ("q", "estado", "tipo", "subtipo", "delegacion", "responsable", "desde", "hasta")


def _parse_pk(raw):
    """Entero positivo o ``None`` (cualquier otra cosa se ignora)."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse_date(raw):
    """Fecha ISO (AAAA-MM-DD) o ``None``."""
    try:
        return date.fromisoformat(str(raw).strip())
    except (TypeError, ValueError):
        return None


def parse_list_params(request, data=None):
    """Lee y valida los parámetros del listado/exportación de atenciones.

    ``data`` son los parámetros efectivos (los de la URL o los recordados en
    la sesión); si no se indica, se usan los de la URL. Devuelve un diccionario
    con los valores ya normalizados (cadenas vacías cuando el parámetro no
    viene o es inválido) más ``date_error`` si el rango de fechas es
    incoherente.
    """
    get = request.GET if data is None else data
    valid_states = {value for value, _label in ATTENTIONS_MODULE.status_options}

    estado = get.get("estado") or ""
    tipo = _parse_pk(get.get("tipo"))
    subtipo = _parse_pk(get.get("subtipo"))
    delegacion = _parse_pk(get.get("delegacion"))
    responsable = _parse_pk(get.get("responsable"))

    desde = _parse_date(get.get("desde"))
    hasta = _parse_date(get.get("hasta"))
    date_error = ""
    if desde and hasta and desde > hasta:
        date_error = "La fecha «Desde» no puede ser posterior a «Hasta»: se ignoró el rango."
        desde = hasta = None

    orden = (get.get("orden") or "").strip()
    if split_order(orden)[0] not in SORT_FIELDS:
        orden = ""

    por_pagina = _parse_pk(get.get("por_pagina"))
    if por_pagina not in PAGE_SIZE_OPTIONS:
        por_pagina = None

    page = str(get.get("page") or "").strip()

    return {
        "q": (get.get("q") or "").strip(),
        "estado": estado if estado in valid_states else "",
        "tipo": str(tipo) if tipo else "",
        "subtipo": str(subtipo) if subtipo else "",
        "delegacion": str(delegacion) if delegacion else "",
        "responsable": str(responsable) if responsable else "",
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "orden": orden,
        "por_pagina": str(por_pagina) if por_pagina else "",
        "page": page,
        "date_error": date_error,
    }


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def _apply_date_range(queryset, desde, hasta):
    """Filtra por fecha de ingreso con límites explícitos (sin ``__date``).

    ``__date`` en MariaDB exige tener cargadas las tablas de zonas horarias;
    comparar contra límites calculados en Python funciona igual en SQLite y
    en MariaDB.
    """
    if desde:
        queryset = queryset.filter(created_at__gte=_day_start(date.fromisoformat(desde)))
    if hasta:
        try:
            limit = _day_start(date.fromisoformat(hasta) + timedelta(days=1))
        except OverflowError:
            limit = None
        if limit is not None:
            queryset = queryset.filter(created_at__lt=limit)
    return queryset


def order_attentions(queryset, orden):
    """Ordena por una clave pública (``-clave`` = descendente).

    Usa el orden común del motor (``order_queryset``): siempre añade ``pk``
    como desempate para que la paginación sea estable.
    """
    return order_queryset(queryset, ATTENTIONS_MODULE, orden)


def attentions_listing_queryset(request, config, data=None):
    """Atenciones del listado/exportación: alcance + filtros + búsqueda + orden.

    ``data`` son los parámetros efectivos (URL o sesión). La búsqueda ``q`` se
    resuelve en la base de datos (``apply_search`` devuelve un queryset).
    Devuelve ``(queryset, params)``.
    """
    params = parse_list_params(request, data)
    queryset = filtered_queryset(request, config, estado=params["estado"])
    if params["tipo"]:
        queryset = queryset.filter(attention_type_id=params["tipo"])
    if params["subtipo"]:
        queryset = queryset.filter(attention_subtype_id=params["subtipo"])
    # La delegación solo se filtra en la vista "Todas": en cualquier otro caso
    # la delegación activa ya acota el listado (y el control no se muestra).
    if params["delegacion"] and get_active_delegation(request) == ALL_DELEGATIONS:
        queryset = queryset.filter(delegation_id=params["delegacion"])
    if params["responsable"]:
        queryset = queryset.filter(responsible_id=params["responsable"])
    queryset = _apply_date_range(queryset, params["desde"], params["hasta"])
    queryset = apply_search(queryset, config.search_fields, params["q"])
    return order_attentions(queryset, params["orden"]), params


def list_querystring(params, **overrides):
    """``?a=1&b=2`` con los parámetros vigentes (vacíos omitidos).

    ``overrides`` reemplaza valores; pasar ``None`` quita el parámetro.
    """
    return build_querystring(params, LIST_PARAM_KEYS, **overrides)


def _type_options(selected):
    options = []
    for item in AttentionType.alive.order_by("code"):
        label = item.name if item.status == "Activo" else f"{item.name} (inactivo)"
        options.append({"value": str(item.pk), "label": label,
                        "selected": str(item.pk) == selected})
    return options


def _subtype_options(selected, type_pk):
    queryset = AttentionSubtype.alive.select_related("attention_type").order_by("code")
    if type_pk:
        queryset = queryset.filter(attention_type_id=type_pk)
    options = []
    for item in queryset:
        label = item.name if item.status == "Activo" else f"{item.name} (inactivo)"
        if not type_pk:
            label = f"{item.attention_type.name} › {label}"
        options.append({"value": str(item.pk), "label": label,
                        "selected": str(item.pk) == selected})
    return options


def _responsible_options(request, config, selected):
    visible = scoped_queryset(request, config).order_by().values("responsible_id")
    users = User.objects.filter(pk__in=visible).order_by(
        "first_name", "last_name", "username",
    )
    return [
        {"value": str(user.pk), "label": user.get_full_name() or user.username,
         "selected": str(user.pk) == selected}
        for user in users
    ]


def _delegation_options(request, selected):
    return [
        {"value": str(item.pk), "label": _deleg_label(item),
         "selected": str(item.pk) == selected}
        for item in allowed_delegations(request.user)
    ]



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
    """Listado de atenciones: búsqueda, filtros, orden por columna y página.

    Parámetros GET (todos opcionales y validados): ``q``, ``estado``, ``tipo``,
    ``subtipo``, ``delegacion`` (solo en la vista "Todas"), ``responsable``,
    ``desde``/``hasta`` (AAAA-MM-DD), ``orden`` (clave o ``-clave``),
    ``por_pagina`` (5, 10, 25 o 50) y ``page``. El último estado usado se
    guarda en la sesión (``CrudListView.get``) y ``?limpiar=1`` lo borra.
    """

    template_name = "portal/crud/attention_list.html"

    def list_keys(self):
        return LIST_STATE_KEYS

    def get_context_data(self, **kwargs):
        # Se salta CrudListView.get_context_data a propósito: ese método usa
        # los filtros genéricos del motor y repetir la consulta solo para
        # descartarla sería trabajo desperdiciado. Este método entrega las
        # mismas claves de contexto que usa la plantilla.
        context = super(CrudListView, self).get_context_data(**kwargs)
        config = self.config
        request = self.request

        queryset, params = attentions_listing_queryset(request, config, self.list_params or {})
        context.update(paginate_listing(config, queryset, params, LIST_STATE_KEYS))

        active = get_active_delegation(request)
        role = get_role(request.user)
        filters_active = any(params[key] for key in FILTER_KEYS)
        base_search = reverse(config.module_key)

        context.update(
            {
                "active_module": config.module_key,
                "config": config,
                "columns": config.columns,
                "query": params["q"],
                "estado": params["estado"],
                "status_options": config.status_options,
                "empty_kind": "results" if filters_active else "records",
                "search_url": base_search,
                "clear_url": f"{base_search}?{CLEAR_PARAM}=1",
                "export_url": reverse(f"{config.module_key}_export")
                + list_querystring(params, page=None, por_pagina=None),
                "new_url": reverse(f"{config.module_key}_new"),
                "detail_url_name": f"{config.module_key}_detail",
                "edit_url_name": f"{config.module_key}_edit",
                "delete_url_name": f"{config.module_key}_delete",
                # --- filtros avanzados ---
                "type_options": _type_options(params["tipo"]),
                "subtype_options": _subtype_options(params["subtipo"], params["tipo"]),
                "show_delegation_filter": active == ALL_DELEGATIONS,
                "delegation_options": (
                    _delegation_options(request, params["delegacion"])
                    if active == ALL_DELEGATIONS else []
                ),
                "show_responsible_filter": bool(role) and role.scope != "own_records",
                "responsible_options": (
                    _responsible_options(request, config, params["responsable"])
                    if role and role.scope != "own_records" else []
                ),
                "date_from": params["desde"],
                "date_to": params["hasta"],
                "date_error": params["date_error"],
                "scope_note": scope_note(request),
                **self.access_flags(),
            }
        )
        return context


def _broadcast_attention(obj, action="created"):
    """Emite en vivo la creación/edición de una atención a su delegación y a ALL."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    payload = {
        "type": "attention_created",
        "id": obj.pk,
        "number": obj.number,
        "solicitante": obj.solicitante_name,
        "fecha": obj.created_at_display,
        "tipo": obj.type_name,
        "subtipo": obj.subtype_name,
        "delegation": obj.delegation.code,
        "delegation_color": obj.delegation.color or "#920000",
        "responsable": obj.responsible_name,
        "estado": obj.status_display,
        "action": action,
    }
    async_to_sync(channel_layer.group_send)(f"atenciones_{obj.delegation.code}", payload)
    async_to_sync(channel_layer.group_send)("atenciones_ALL", payload)


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
        _broadcast_attention(obj, "created")
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

    template_name = "portal/crud/attention_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.attention_form_context(context["form"]))
        return context

    def form_valid(self, form):
        obj = form.save()
        _broadcast_attention(obj, "updated")
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
    """Exporta a Excel las atenciones filtradas y con alcance.

    El archivo se llama ``atenciones_<AAAAMMDD_HHMM>_<usuario>.xlsx``.
    """

    action = "export"

    def get(self, request, *args, **kwargs):
        # Mismos filtros y orden que el listado; se exportan TODAS las filas
        # del resultado (sin paginar).
        queryset, params = attentions_listing_queryset(request, self.config)
        rows_all = list(queryset)

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
        sheet.freeze_panes = "A2"

        filename = export_filename(self.config.slug, request.user)
        detail = " ".join(
            f"{key}={params[key]!r}" for key in FILTER_KEYS + ("orden",) if params[key]
        )
        audit(
            request, "export", module="attentions",
            object_repr=f"{len(rows_all)} registros",
            detail=f"{filename} · {detail}".rstrip(" ·"),
        )
        return xlsx_response(workbook, filename)


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
