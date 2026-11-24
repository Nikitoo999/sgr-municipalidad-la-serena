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
    toolbar_links=(("Organigrama", "organization_chart"),),
)

register_module(ORGANIZATIONS_MODULE)


# ---------------------------------------------------------------------------
# Directiva de la organización (organigrama): cargos base + cargos creados.
# ---------------------------------------------------------------------------

from django.contrib import messages  # noqa: E402
from django.contrib.auth.mixins import LoginRequiredMixin  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.db.models import Count, Q  # noqa: E402
from django.shortcuts import redirect  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.http import url_has_allowed_host_and_scheme  # noqa: E402
from django.views import View  # noqa: E402
from django.views.generic import TemplateView  # noqa: E402

from portal.validators import normalize_phone, validate_full_name, validate_rut  # noqa: E402
from sgr_core.models import DirectiveRole, OrganizationMember  # noqa: E402

from ..access import ModulePermissionMixin  # noqa: E402
from ..audit import audit  # noqa: E402
from .views import CrudBaseMixin, resolve_object_or_deny, scoped_queryset  # noqa: E402


#: Máximo de organizaciones en la columna izquierda (el buscador acota el resto).
CHART_ORG_LIMIT = 60


def _safe_next(request):
    """URL de retorno del formulario, solo si es del mismo sitio."""
    destino = request.POST.get("next") or ""
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return destino
    return ""


def _directiva_redirect(request, organization):
    """Vuelve al organigrama (o a la página indicada en ``next``)."""
    return redirect(_safe_next(request) or f"{reverse('organization_chart')}?org={organization.pk}")


def _roles_redirect(request):
    return redirect(_safe_next(request) or "organization_chart")


def _role_form_values(request, role=None):
    """Valida nombre, nivel y orden de un cargo directivo. Devuelve (datos, errores)."""
    errors = []
    name = " ".join((request.POST.get("name") or "").split())[:60]
    if role is not None and role.is_base:
        name = role.name  # los cargos base no se renombran
    elif len(name) < 3:
        errors.append("Escribe el nombre del cargo directivo (al menos 3 caracteres).")
    else:
        repetido = DirectiveRole.objects.filter(name__iexact=name, deleted_at__isnull=True)
        if role is not None:
            repetido = repetido.exclude(pk=role.pk)
        if repetido.exists():
            errors.append(f"El cargo «{name}» ya existe.")
    try:
        level = int(request.POST.get("level") or DirectiveRole.Level.DELEGATES)
    except (TypeError, ValueError):
        level = 0
    if level not in DirectiveRole.Level.values:
        errors.append("Elige un nivel jerárquico válido.")
    try:
        order = int(request.POST.get("order") or 100)
    except (TypeError, ValueError):
        order = -1
    if not 1 <= order <= 999:
        errors.append("El orden debe ser un número entre 1 y 999.")
    return {"name": name, "level": level, "order": order}, errors


def _roles_en_uso():
    """{role_id: integrantes vigentes en todas las organizaciones}."""
    return dict(
        OrganizationMember.objects.filter(deleted_at__isnull=True)
        .values("role_id").annotate(n=Count("pk")).values_list("role_id", "n")
    )


class OrganizationChartView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, TemplateView):
    """Organigrama de las organizaciones comunitarias, por niveles jerárquicos.

    Columna izquierda: organizaciones del alcance (buscador por nombre o
    territorio). Derecha: la directiva de la organización elegida, con los
    cargos ocupados y vacantes ordenados por nivel, más la gestión de cargos.
    """

    template_name = "portal/organization_chart.html"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request = self.request
        base = scoped_queryset(request, self.config, ordering=("name",))
        q = " ".join((request.GET.get("q") or "").split())[:80]
        listado = base
        if q:
            listado = listado.filter(Q(name__icontains=q) | Q(territory__icontains=q))
        total = listado.count()
        organizaciones = list(
            listado.select_related("delegation").annotate(
                directivos=Count("members", filter=Q(members__deleted_at__isnull=True)),
            )[:CHART_ORG_LIMIT]
        )
        seleccionada = None
        org_pk = request.GET.get("org") or ""
        if org_pk.isdigit():
            seleccionada = base.select_related("delegation").filter(pk=int(org_pk)).first()
        if seleccionada is None and organizaciones:
            seleccionada = organizaciones[0]

        niveles, cubiertos, vacantes = [], 0, 0
        if seleccionada is not None:
            integrantes = {m.role_id: m for m in seleccionada.directiva}
            roles = {
                r.pk: r for r in DirectiveRole.objects.filter(deleted_at__isnull=True, status="Activo")
            }
            for m in integrantes.values():  # un cargo inactivo con integrante igual se muestra
                roles.setdefault(m.role_id, m.role)
            for valor, etiqueta in DirectiveRole.Level.choices:
                nodos = []
                for role in sorted(roles.values(), key=lambda r: (r.order, r.name)):
                    if role.level != valor:
                        continue
                    miembro = integrantes.get(role.pk)
                    nodos.append({"role": role, "member": miembro})
                    if miembro:
                        cubiertos += 1
                    else:
                        vacantes += 1
                if nodos:
                    niveles.append({"value": valor, "label": etiqueta, "nodes": nodos})

        en_uso = _roles_en_uso()
        catalogo = list(DirectiveRole.objects.filter(deleted_at__isnull=True))
        for role in catalogo:
            role.uso = en_uso.get(role.pk, 0)
        context.update({
            "config": self.config,
            "q": q,
            "organizaciones": organizaciones,
            "total_organizaciones": total,
            "limite": CHART_ORG_LIMIT,
            "org": seleccionada,
            "niveles": niveles,
            "cubiertos": cubiertos,
            "vacantes": vacantes,
            "total_cargos": cubiertos + vacantes,
            "catalogo": catalogo,
            "level_choices": DirectiveRole.Level.choices,
            "volver": request.get_full_path(),
            **self.access_flags(),
        })
        return context


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
        datos, errors = _role_form_values(request)
        if errors:
            messages.error(request, " ".join(errors))
        else:
            role = DirectiveRole.objects.create(**datos)
            audit(request, "create", module="organizations", object_repr=role.name,
                  detail=f"Cargo directivo creado ({role.get_level_display()}, orden {role.order})")
            messages.success(request, f"Cargo directivo «{role.name}» creado.")
        return _roles_redirect(request)


class DirectiveRoleUpdateView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Cambia nombre, nivel u orden de un cargo (los cargos base no se renombran)."""

    action = "edit"

    def post(self, request, *args, **kwargs):
        role = DirectiveRole.objects.filter(pk=self.kwargs["role_pk"], deleted_at__isnull=True).first()
        if role is None:
            messages.error(request, "El cargo directivo ya no existe.")
            return _roles_redirect(request)
        datos, errors = _role_form_values(request, role)
        if errors:
            messages.error(request, " ".join(errors))
            return _roles_redirect(request)
        antes = f"{role.name} ({role.get_level_display()}, orden {role.order})"
        role.name, role.level, role.order = datos["name"], datos["level"], datos["order"]
        role.save(update_fields=["name", "level", "order", "updated_at"])
        audit(request, "edit", module="organizations", object_repr=role.name,
              detail=f"Cargo directivo: {antes} → {role.name} ({role.get_level_display()}, orden {role.order})")
        messages.success(request, f"Cargo «{role.name}» actualizado.")
        return _roles_redirect(request)


class DirectiveRoleDeleteView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Elimina un cargo creado que nadie ocupa (borrado lógico; solo superadmin)."""

    action = "delete"

    def post(self, request, *args, **kwargs):
        role = DirectiveRole.objects.filter(pk=self.kwargs["role_pk"], deleted_at__isnull=True).first()
        if role is None:
            messages.error(request, "El cargo directivo ya no existe.")
        elif role.is_base:
            messages.error(request, f"«{role.name}» es un cargo base: no se elimina.")
        elif OrganizationMember.objects.filter(role=role, deleted_at__isnull=True).exists():
            messages.error(
                request,
                f"«{role.name}» está ocupado en alguna organización: déjalo vacante antes de eliminarlo.",
            )
        else:
            role.deleted_at = timezone.now()
            role.save(update_fields=["deleted_at", "updated_at"])
            audit(request, "delete", module="organizations", object_repr=role.name,
                  detail="Cargo directivo eliminado")
            messages.success(request, f"Cargo «{role.name}» eliminado.")
        return _roles_redirect(request)
