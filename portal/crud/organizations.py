"""Configuración del mantenedor de Organizaciones comunitarias (Unidad 3).

Base de juntas de vecinos y organizaciones funcionales que entregó la
Municipalidad (``base datos JJVV sin verificar.xlsx``). Se carga y limpia con
``python manage.py seed_organizaciones`` y aquí se consulta, filtra, exporta y
mantiene. Alcance: la delegación activa del usuario (con "Todas" se ven todas,
incluidas las que aún no tienen delegación asignada).
"""

from sgr_core.models import CommunityOrganization

from ..access import ALL_DELEGATIONS, allowed_delegations, get_active_delegation, get_role
from .config import (
    CELL_DELEGATION, CELL_STATUS, ColumnSpec, FilterSpec, ModuleConfig, register_module,
)
from .forms import CommunityOrganizationForm


def organizations_scope(request, queryset):
    """Organizaciones de la delegación activa (todas con el contexto "Todas")."""
    if get_role(request.user) is None:
        return queryset.none()
    active = get_active_delegation(request)
    if active is None:
        return queryset.none()
    if active != ALL_DELEGATIONS:
        queryset = queryset.filter(delegation_id=active.pk)
    return queryset


def category_options(request):
    return list(CommunityOrganization.Category.choices)


def delegation_options(request):
    return [(d.pk, f"{d.code} · {d.name}") for d in allowed_delegations(request.user)]


def verified_options(request):
    return [("si", "Verificadas"), ("no", "Sin verificar")]


def filter_verified(queryset, value):
    return queryset.filter(verified=(value == "si"))


ORGANIZATIONS_MODULE = ModuleConfig(
    module_key="organizations",
    slug="organizaciones",
    model=CommunityOrganization,
    form_class=CommunityOrganizationForm,
    list_title="Organizaciones comunitarias",
    singular_label="Organización",
    gender="f",
    columns=(
        ColumnSpec("name", "Nombre", sort_key="nombre", sort_fields=("name",)),
        ColumnSpec("category_label", "Categoría", sort_key="categoria", sort_fields=("category", "name")),
        ColumnSpec("delegation", "Delegación", cell=CELL_DELEGATION,
                   sort_key="delegacion", sort_fields=("delegation__code", "name")),
        ColumnSpec("territory", "Territorio", sort_key="territorio", sort_fields=("territory", "name")),
        ColumnSpec("members_display", "Socios", sort_key="socios", sort_fields=("active_members",)),
        ColumnSpec("registry_number", "N° registro P.J.", sort_key="registro", sort_fields=("registry_number",)),
        ColumnSpec("legal_address", "Domicilio legal"),
        ColumnSpec("verified_display", "Verificación", sort_key="verificada", sort_fields=("verified", "name")),
        ColumnSpec("status", "Estado", cell=CELL_STATUS, sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("name", "territory", "legal_address", "registry_number", "delegation__name"),
    search_placeholder="Buscar por nombre, territorio, domicilio o N° de registro...",
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    filters=(
        FilterSpec("categoria", "Categoría", "category", options=category_options, empty_label="Todas"),
        FilterSpec("delegacion", "Delegación", "delegation_id", options=delegation_options, empty_label="Todas"),
        FilterSpec("verificada", "Verificación", "verified", options=verified_options,
                   apply=filter_verified, empty_label="Todas"),
    ),
    ordering=("name",),
    default_sort="nombre",
    page_size_options=(15, 30, 50),
    select_related=("delegation",),
    scope=organizations_scope,
)

register_module(ORGANIZATIONS_MODULE)
