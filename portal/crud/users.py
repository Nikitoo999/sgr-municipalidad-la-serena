"""Configuración del mantenedor de Usuarios (Parte 5, Etapa 2).

Solo la declara: el motor (``portal.crud.views``) hace todo el trabajo. El
listado se acota con :func:`users_scope` (misma regla de rango + delegación que
``portal.access.visible_users``) y el borrado nunca es físico: el guard impide
eliminar al único superusuario y el modelo desactiva la cuenta.

Bloque 2A: orden por columna y filtros propios por Estado (cuenta activa o
inactiva), Rol y Delegación. Las opciones de Rol y Delegación salen de los
usuarios que el operador ya puede ver, así el filtro nunca amplía el alcance.
"""

from django.db.models import Q

from ..access import get_role
from ..access import allowed_delegations
from sgr_core.models import Delegation, Role
from sgr_core.roles import SCOPE_RANKS
from operaciones.models import Employee

from .config import CELL_STATUS, CELL_DELEGATION, ColumnSpec, FilterSpec, ModuleConfig, register_module
from .forms import UserForm


def users_scope(request, queryset):
    """Usuarios visibles para el operador (mismo criterio que ``visible_users``).

    - Superusuario ve a todos (incluidos otros superusuarios).
    - Un superusuario NUNCA es visible para quien no es superusuario.
    - El resto ve solo usuarios de menor rango, con rol Activo, sin rol de
      sistema virtual y cuya delegación base esté entre las permitidas.
    """
    role = get_role(request.user)
    if role is None:
        return queryset.none()
    if getattr(request.user, "is_superuser", False):
        return queryset
    delegations = allowed_delegations(request.user)
    if not delegations:
        return queryset.none()
    lower_scopes = [
        scope for scope, rank in SCOPE_RANKS.items() if rank < role.rank
    ]
    if not lower_scopes:
        return queryset.none()
    return queryset.filter(
        user__is_superuser=False,
        delegation_id__in=[delegation.pk for delegation in delegations],
        role__scope__in=lower_scopes,
        role__status="Activo",
    ).distinct()


def user_delete_guard(employee, request=None):
    """Bloquea el borrado del propio operador o del último superusuario.

    El borrado es lógico (nunca físico) y desactiva la cuenta; aquí solo se
    impiden los casos que dejarían el sistema sin acceso. Devuelve el mensaje a
    mostrar o cadena vacía si se puede eliminar.
    """
    if request is not None and request.user.pk == employee.user_id:
        return "No puedes eliminar tu propio usuario."
    if employee.user.is_superuser:
        otros = Employee.objects.filter(
            user__is_superuser=True, deleted_at__isnull=True
        ).exclude(pk=employee.pk).count()
        if otros == 0:
            return (
                "No se puede eliminar el último usuario administrador del "
                "sistema. Crea otro administrador antes de eliminarlo."
            )
    return ""


def _visible_employees(request):
    return users_scope(request, Employee.alive.all())


def role_options(request):
    """Roles de los usuarios visibles (filtro propio "Rol")."""
    roles = Role.objects.filter(
        pk__in=_visible_employees(request).values("role_id"),
    ).order_by("code")
    return [(role.pk, f"{role.code} · {role.name}") for role in roles]


def delegation_options(request):
    """Delegaciones (base o autorizadas) de los usuarios visibles."""
    visible = _visible_employees(request)
    delegations = Delegation.objects.filter(
        Q(pk__in=visible.values("delegation_id"))
        | Q(pk__in=visible.values("authorized_delegations"))
    ).order_by("code")
    return [(d.pk, f"{d.code} · {d.name}") for d in delegations]


def filter_by_delegation(queryset, value):
    """Usuarios cuya delegación base o autorizada es la elegida."""
    return queryset.filter(
        Q(delegation_id=value) | Q(authorized_delegations__id=value)
    ).distinct()


def filter_by_status(queryset, value):
    """El estado del usuario es el de su cuenta (``user.is_active``)."""
    return queryset.filter(user__is_active=(value == "Activo"))


USERS_MODULE = ModuleConfig(
    module_key="users",
    slug="usuarios",
    model=Employee,
    form_class=UserForm,
    list_title="Usuarios",
    singular_label="Usuario",
    gender="m",
    columns=(
        ColumnSpec("rut", "RUT", sort_key="rut", sort_fields=("rut",)),
        ColumnSpec("full_name", "Nombre", sort_key="nombre",
                   sort_fields=("user__first_name", "user__last_name", "user__username")),
        ColumnSpec("email", "Correo", sort_key="correo", sort_fields=("user__email",)),
        ColumnSpec("role_code", "Rol", sort_key="rol", sort_fields=("role__code",)),
        ColumnSpec("delegations", "Delegaciones", cell=CELL_DELEGATION,
                   sort_key="delegacion", sort_fields=("delegation__code",)),
        # Ascendente muestra primero los activos.
        ColumnSpec("status_label", "Estado", cell=CELL_STATUS,
                   sort_key="estado", sort_fields=("-user__is_active",)),
    ),
    search_fields=(
        "rut", "user__first_name", "user__last_name", "user__email",
        "user__username", "role__name", "role__code", "delegation__name",
        "delegation__code",
    ),
    search_placeholder="Buscar por RUT, nombre, correo, rol o delegación...",
    status_field=None,
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    status_filter=filter_by_status,
    filters=(
        FilterSpec("rol", "Rol", "role_id", options=role_options),
        FilterSpec("delegacion", "Delegación", "delegation_id",
                   options=delegation_options, apply=filter_by_delegation,
                   empty_label="Todas"),
    ),
    ordering=("user__first_name", "user__last_name", "rut"),
    default_sort="nombre",
    select_related=("user", "role", "delegation"),
    row_label=lambda employee: employee.full_name,
    scope=users_scope,
    delete_guard=user_delete_guard,
    form_template="portal/crud/users_form.html",
)

register_module(USERS_MODULE)
