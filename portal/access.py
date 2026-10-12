"""Control de acceso del lado servidor: permisos por rol y alcance por delegación.

Ocultar botones en la interfaz NO es control de acceso: todas las vistas protegidas
pasan por `has_perm` / `allowed_delegations`.
"""
from django.db.models import Q

from sgr_core.models import Delegation, Role

SUPERADMIN = "superadministrador"
COORDINADOR = "coordinador"
DELEGADO = "delegado_municipal"
FUNCIONARIO = "funcionario"

PERMISSIONS = {
    "delegation.view": "Consultar delegaciones",
    "delegation.create": "Crear delegaciones",
    "delegation.edit": "Editar delegaciones",
    "delegation.delete": "Desactivar delegaciones",
    "role.view": "Consultar roles",
    "role.create": "Crear roles",
    "role.edit": "Editar roles",
    "role.delete": "Desactivar roles",
    "user.view": "Consultar usuarios",
    "user.create": "Crear usuarios",
    "user.edit": "Editar usuarios",
    "user.delete": "Desactivar usuarios",
    "catalog.view": "Consultar ítems y catálogos de atención",
    "catalog.manage": "Administrar ítems y catálogos de atención",
    "attention.view": "Consultar atenciones",
    "attention.create": "Ingresar atenciones",
}

_ALL = list(PERMISSIONS)
ROLE_DEFINITIONS = {
    SUPERADMIN: {
        "name": "Superadministrador", "scope": Role.SCOPE_ALL,
        "description": "Acceso total al sistema.", "perms": _ALL,
    },
    COORDINADOR: {
        "name": "Coordinador", "scope": Role.SCOPE_ALL,
        "description": "Supervisa todas las delegaciones y administra catálogos y usuarios.",
        "perms": ["delegation.view", "role.view", "user.view", "user.create", "user.edit", "user.delete",
                  "catalog.view", "catalog.manage", "attention.view", "attention.create"],
    },
    DELEGADO: {
        "name": "Delegado municipal", "scope": Role.SCOPE_DELEGATIONS,
        "description": "Gestiona su delegación (o las autorizadas).",
        "perms": ["delegation.view", "user.view", "user.create", "user.edit",
                  "catalog.view", "attention.view", "attention.create"],
    },
    FUNCIONARIO: {
        "name": "Funcionario", "scope": Role.SCOPE_OWN,
        "description": "Registra atenciones en su delegación.",
        "perms": ["catalog.view", "attention.view", "attention.create"],
    },
}
BASE_ROLE_CODES = tuple(ROLE_DEFINITIONS)

# Qué roles puede asignar cada rol (evita escalada de privilegios).
ASSIGNABLE = {
    SUPERADMIN: set(BASE_ROLE_CODES),
    COORDINADOR: {COORDINADOR, DELEGADO, FUNCIONARIO},
    DELEGADO: {FUNCIONARIO},
}


def get_employee(user):
    if not getattr(user, "is_authenticated", False):
        return None
    emp = getattr(user, "employee", None)
    if emp is None or emp.deleted_at is not None:
        return None
    return emp


def get_role(user):
    emp = get_employee(user)
    role = getattr(emp, "app_role", None)
    return role if role and role.is_active else None


def user_permissions(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return frozenset()
    if user.is_superuser:
        return frozenset(PERMISSIONS)
    cached = getattr(user, "_sgr_perms", None)
    if cached is not None:
        return cached
    role = get_role(user)
    perms = frozenset(role.permissions.values_list("codename", flat=True)) if role else frozenset()
    user._sgr_perms = perms
    return perms


def has_perm(user, codename):
    return codename in user_permissions(user)


def allowed_delegations(user, only_active=False):
    """Delegaciones sobre las que el usuario puede operar (validado en servidor)."""
    qs = Delegation.objects.filter(deleted_at__isnull=True)
    if only_active:
        qs = qs.filter(is_active=True)
    if user.is_superuser:
        return qs
    emp, role = get_employee(user), get_role(user)
    if not emp or not role:
        return qs.none()
    if role.scope == Role.SCOPE_ALL:
        return qs
    if role.scope == Role.SCOPE_DELEGATIONS:
        return qs.filter(Q(pk=emp.delegation_id) | Q(pk__in=emp.authorized_delegations.values("pk")))
    return qs.filter(pk=emp.delegation_id)


def assignable_role_codes(user):
    if user.is_superuser:
        return set(BASE_ROLE_CODES) | set(Role.objects.values_list("code", flat=True))
    role = get_role(user)
    return ASSIGNABLE.get(role.code, set()) if role else set()


def active_delegation(request):
    """Delegación activa de la sesión; siempre revalidada contra las autorizadas."""
    allowed = allowed_delegations(request.user, only_active=True)
    pk = request.session.get("active_delegation_id")
    if pk:
        found = allowed.filter(pk=pk).first()
        if found:
            return found
    emp = get_employee(request.user)
    if emp:
        own = allowed.filter(pk=emp.delegation_id).first()
        if own:
            return own
    return allowed.order_by("code", "name").first()
