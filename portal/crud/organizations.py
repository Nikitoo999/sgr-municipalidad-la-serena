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
    form_template="portal/crud/organization_form.html",
)

register_module(ORGANIZATIONS_MODULE)


# ---------------------------------------------------------------------------
# Directiva de la organización (organigrama): cargos base + cargos creados.
# ---------------------------------------------------------------------------

from django.contrib import messages  # noqa: E402
from django.contrib.auth.mixins import LoginRequiredMixin  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.shortcuts import redirect  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.http import url_has_allowed_host_and_scheme  # noqa: E402
from django.views import View  # noqa: E402

from portal.validators import normalize_phone, validate_full_name, validate_rut  # noqa: E402
from sgr_core.models import DirectiveRole, OrganizationMember  # noqa: E402

from ..access import ModulePermissionMixin  # noqa: E402
from ..audit import audit  # noqa: E402
from .views import CrudBaseMixin, resolve_object_or_deny, scoped_queryset  # noqa: E402


def _directiva_redirect(request, organization):
    return redirect("organizations_detail", pk=organization.pk)


class OrganizationMemberSaveView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Asigna o actualiza el integrante de un cargo de la directiva (solo POST).

    Una organización tiene un integrante vigente por cargo: si el cargo ya
    estaba ocupado, se actualizan sus datos (la auditoría guarda el cambio).
    """

    action = "edit"

    def post(self, request, *args, **kwargs):
        organization = resolve_object_or_deny(
            request, self.config, scoped_queryset(request, self.config), self.kwargs["pk"],
        )
        role = DirectiveRole.objects.filter(
            pk=request.POST.get("role") or 0, deleted_at__isnull=True, status="Activo",
        ).first()
        errors = []
        if role is None:
            errors.append("Elige el cargo directivo.")
        try:
            full_name = validate_full_name(request.POST.get("full_name"))
        except ValidationError as exc:
            errors.extend(exc.messages)
            full_name = ""
        rut = (request.POST.get("rut") or "").strip()
        if rut:
            try:
                rut = validate_rut(rut)
            except ValidationError as exc:
                errors.extend(exc.messages)
        phone = (request.POST.get("phone") or "").strip()
        if phone:
            try:
                phone = normalize_phone(phone)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if errors:
            messages.error(request, "No se pudo guardar el integrante: " + " ".join(errors))
            return _directiva_redirect(request, organization)
        member = OrganizationMember.objects.filter(
            organization=organization, role=role, deleted_at__isnull=True,
        ).first()
        anterior = member.full_name if member else ""
        if member is None:
            member = OrganizationMember(organization=organization, role=role)
        member.full_name, member.rut, member.phone = full_name, rut, phone
        member.save()
        audit(
            request, "edit", module="organizations", object_repr=organization.name,
            detail=f"Directiva: {role.name} {anterior + ' → ' if anterior else ''}{full_name}",
        )
        messages.success(request, f"{full_name} quedó como {role.name} de {organization.name}.")
        return _directiva_redirect(request, organization)


class OrganizationMemberRemoveView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Deja vacante un cargo de la directiva (borrado lógico, solo POST)."""

    action = "edit"

    def post(self, request, *args, **kwargs):
        organization = resolve_object_or_deny(
            request, self.config, scoped_queryset(request, self.config), self.kwargs["pk"],
        )
        member = OrganizationMember.objects.filter(
            pk=self.kwargs["member_pk"], organization=organization, deleted_at__isnull=True,
        ).select_related("role").first()
        if member is None:
            messages.error(request, "El integrante ya no está en la directiva.")
        else:
            member.deleted_at = timezone.now()
            member.save(update_fields=["deleted_at", "updated_at"])
            audit(request, "delete", module="organizations", object_repr=organization.name,
                  detail=f"Directiva: {member.role.name} vacante (antes {member.full_name})")
            messages.success(request, f"El cargo {member.role.name} quedó vacante.")
        return _directiva_redirect(request, organization)


class DirectiveRoleCreateView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Crea un cargo directivo nuevo (Vicepresidente/a, Encargado/a de...)."""

    action = "create"

    def post(self, request, *args, **kwargs):
        name = " ".join((request.POST.get("name") or "").split())[:60]
        destino = request.POST.get("next") or ""
        if len(name) < 3:
            messages.error(request, "Escribe el nombre del cargo directivo (al menos 3 caracteres).")
        elif DirectiveRole.objects.filter(name__iexact=name, deleted_at__isnull=True).exists():
            messages.info(request, f"El cargo «{name}» ya existe.")
        else:
            DirectiveRole.objects.create(name=name, order=100)
            audit(request, "create", module="organizations", object_repr=name,
                  detail="Cargo directivo creado")
            messages.success(request, f"Cargo directivo «{name}» creado.")
        if destino and url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
        ):
            return redirect(destino)
        return redirect("organizations")
