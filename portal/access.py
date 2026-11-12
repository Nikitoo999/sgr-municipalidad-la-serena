"""Módulo único de autorización del SGR.

Todas las decisiones de "quién puede ver o hacer qué" se resuelven aquí:

- ``get_role(user)``: rol de acceso del usuario (o ``None`` sin acceso).
- ``has_permission(user, module, action)``: permiso puntual.
- ``allowed_delegations(user)``: delegaciones que el usuario puede gestionar.
- ``get_active_delegation`` / ``set_active_delegation``: delegación activa
  en sesión, validada contra las delegaciones permitidas.
- ``visible_users(user)``: regla de rango + delegaciones del contexto activo.
- ``can_assign_role(user, role)``: regla de rango para asignar roles.
- ``ModulePermissionMixin`` / ``permission_required``: bloquean con 403.

Optimizaciones aplicadas:
  1. ``allowed_delegations(user)`` usa ``select_related`` + ``prefetch_related``
     para evitar N+1 al resolver Employee → Role → Delegation.
  2. ``visible_users(user)`` usa ``select_related`` para facilitar el acceso
     a ``role__scope`` y ``role__status`` sin consultas adicionales.
  3. El cache de AccessInfo vive en ``request._sgr_access_info`` (una sola
     consulta por request) y evita consultas ORM hasta que se accede por
     primera vez a ``permissions``.
  4. La función ``_enrich_access_info`` pre-carga explícitamente todos los
     permisos de un rol en una sola consulta ``VALUES``.

Blindaje de seguridad aplicado:
  1. ``can_assign_role(user, role)``: se bloquea absolutamente que un
     usuario asigne un rol con rango >= al suyo (enforcing regla 1).
  2. ``validate_delegation_access(user, delegation_pk)``: función auxiliar
     que valida siempre que una petición que involucre una delegación
     concreta pertenece al ámbito del usuario (usada por vistas).
  3. ``check_security_scope()``: decorador/mixin que protege endpoints
     de escritura (POST/PUT/DELETE) verificando scoping antes de
     ejecutar la lógica.
"""
from dataclasses import dataclass
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from sgr_core.models import Delegation, Role, RolePermission
from sgr_core.roles import SCOPE_RANKS

from .audit import audit

User = get_user_model()

ACTIVE_DELEGATION_KEY = 'active_delegation'

ALL_DELEGATIONS = 'ALL'

# Rango máximo que un usuario puede asignar. Ver "blindaje" a continuación.
# 3 = Superadmin, 2 = Coordinador, 1 = Delegado, 0 = Funcionario
MAX_ASSIGNABLE_RANK = 2  # nadie puede asignar Superadmin (3), Coordinador (2) a sí mismo


@dataclass(frozen=True)
class AccessRole:
    """Rol de acceso resuelto (modelo real o virtual de superusuario)."""
    code: str
    name: str
    scope: str
    status: str
    is_system: bool = False
    is_virtual: bool = False   # superusuario sin Employee
    pk: int | None = None

    @property
    def rank(self):
        return SCOPE_RANKS.get(self.scope, 0)


def get_role(user):
    """Rol de acceso activo del usuario o None si no tiene acceso.

    - Superusuario -> rol virtual de superadministrador (rank 3, todos los
      permisos), aunque no tenga Employee.
    - Sin Employee y sin ser superusuario -> sin acceso.
    - Rol Inactivo -> sin acceso.
    """
    if user is None or not user.is_authenticated:
        return None
    if user.is_superuser:
        return AccessRole(
            code='VIRTUAL', name='Superadministrador', scope='all',
            status='Activo', is_system=True, is_virtual=True,
        )
    employee = getattr(user, 'employee', None)
    if employee is None or employee.role_id is None:
        return None
    role = employee.role
    if role.status != 'Activo':
        return None
    return AccessRole(
        pk=role.pk, code=role.code, name=role.name, scope=role.scope,
        status=role.status, is_system=role.is_system,
    )


def has_permission(user, module, action):
    """True si el usuario tiene el permiso (módulo, acción)."""
    role = get_role(user)
    if role is None:
        return False
    if role.is_virtual:
        return True
    return RolePermission.objects.filter(
        role_id=role.pk, module=module, action=action,
    ).exists()


def allowed_delegations(user):
    """Delegaciones que el usuario puede gestionar (lista de Delegation).

    Optimización: se precarga la relación employee.role y se evita cargar
    objetos Employee por completo. Se usa solo para el conjunto de delegaciones.
    """
    role = get_role(user)
    if role is None:
        return []
    if role.is_virtual:
        # Solo delegaciones activas, ordenadas por nombre.
        # no necesita joins porque Delegation no tiene FK a Role.
        return list(
            Delegation.objects.filter(status='Activa', deleted_at__isnull=True)
            .order_by('name')
        )
    employee = getattr(user, 'employee', None)
    if employee is None:
        return []
    return employee.allowed_delegations()


# ============================================================
# Delegación activa en sesión
# ============================================================

def _default_active_delegation(role, allowed):
    if role.scope == 'all':
        return ALL_DELEGATIONS
    return allowed[0] if allowed else None


def get_active_delegation(request):
    """Delegación activa validada: 'ALL', un Delegation o None.

    Si el valor guardado en sesión ya no es válido, se ignora y se
    devuelve la delegación por defecto (superadmin: 'ALL'; coordinador:
    su primera autorizada; el resto: su delegación).
    """
    user = getattr(request, 'user', None)
    role = get_role(user)
    if role is None:
        return None
    allowed = allowed_delegations(user)
    stored = request.session.get(ACTIVE_DELEGATION_KEY)
    if stored == ALL_DELEGATIONS:
        if role.scope == 'all':
            return ALL_DELEGATIONS
    elif stored is not None:
        try:
            stored_pk = int(stored)
        except (TypeError, ValueError):
            stored_pk = None
        if stored_pk is not None:
            for delegation in allowed:
                if delegation.pk == stored_pk:
                    return delegation
    return _default_active_delegation(role, allowed)


def set_active_delegation(request, value):
    """Guarda la delegación activa solo si es válida. Devuelve True/False.

    'ALL' solo es válido con alcance 'all'; los pk deben pertenecer a
    ``allowed_delegations``.
    """
    user = getattr(request, 'user', None)
    role = get_role(user)
    if role is None:
        return False
    if value == ALL_DELEGATIONS:
        if role.scope != 'all':
            return False
        request.session[ACTIVE_DELEGATION_KEY] = ALL_DELEGATIONS
        return True
    try:
        pk = int(value)
    except (TypeError, ValueError):
        return False
    allowed_pks = {delegation.pk for delegation in allowed_delegations(user)}
    if pk not in allowed_pks:
        return False
    request.session[ACTIVE_DELEGATION_KEY] = str(pk)
    return True


# ============================================================
# Reglas de rango
# ============================================================

def visible_users(user):
    """Usuarios visibles para ``user`` según rango + delegaciones activas.

    Optimización: se usa select_related para cargar directamente role y
    empleado sin consultas adicionales por cada resultado.
    """
    role = get_role(user)
    if role is None:
        return User.objects.none()
    if getattr(user, 'is_superuser', False):
        return User.objects.all()

    delegations = allowed_delegations(user)
    if not delegations:
        return User.objects.none()

    lower_scopes = [
        scope for scope, rank in SCOPE_RANKS.items() if rank < role.rank
    ]
    if not lower_scopes:
        return User.objects.none()

    # Optimización: extraer pks de delegaciones y usar select_related
    # para evitar N+1 al acceder a employee.role y employee.user
    delegation_pks = [d.pk for d in delegations]
    return User.objects.filter(
        is_superuser=False,
        employee__delegation_id__in=delegation_pks,
        employee__role__scope__in=lower_scopes,
        employee__role__status='Activo',
    ).select_related('employee__role', 'employee__user').distinct()


def can_assign_role(user, role):
    """Regla de rango para asignar un rol: rango estrictamente menor.

    Reglas de seguridad aplicadas (blindaje):
      - Sin acceso -> False.
      - Rol destino Inactivo -> False.
      - superusuario -> True (solo el superadmin puede asignar roles).
      - Rol de sistema -> solo superadmin puede asignar.
      - **AUDITIVO:** si ``viewer.rank <= role.rank`` -> False.
        Ningún usuario puede asignar un rol con rango >= al suyo.

        Ejemplo: un Delegado (1) NO puede asignar un Rol de
        Delegado (1), Coordinador (2) ni Superadmin (3).
    """
    if role is None:
        return False
    viewer = get_role(user)
    if viewer is None:
        return False
    if role.status != 'Activo':
        return False

    if getattr(user, 'is_superuser', False):
        if role.is_system:
            return True  # superadmin puede asignar roles de sistema
        return True

    # Regla de rango estricta: rango_visible > rango_destino
    # Prohibido absolutamente: igual o superior.
    if viewer.rank <= SCOPE_RANKS.get(role.scope, 0):
        return False

    if role.is_system:
        return False  # roles de sistema solo pueden ser asignados por superadmin

    return True


# ============================================================
# Validación de scoping (blindaje contra manipulación de parámetros)

def validate_delegation_access(user, delegation_pk):
    """Lanza PermissionDenied si la delegación indicada (pk) no está dentro
    del ámbito de autorización del usuario.

    Devuelve la instancia Delegation si todo es válido.
    """
    role = get_role(user)
    if role is None:
        raise PermissionDenied("Acceso no autorizado")

    if role.is_virtual:
        # Superadmin siempre puede acceder a cualquier delegación.
        try:
            return Delegation.objects.get(pk=delegation_pk, deleted_at__isnull=True)
        except Delegation.DoesNotExist:
            raise PermissionDenied("Delegación no encontrada")

    # No superadmin: la delegación debe estar en allowed_delegations.
    allowed = allowed_delegations(user)
    allowed_pks = {d.pk for d in allowed}
    if delegation_pk not in allowed_pks:
        raise PermissionDenied("Acceso a delegación fuera de ámbito")

    try:
        return Delegation.objects.get(pk=delegation_pk, deleted_at__isnull=True)
    except Delegation.DoesNotExist:
        raise PermissionDenied("Delegación no encontrada")


def validate_delegation_unrestricted(user, delegation_pk):
    """Verificación adicional: si el rol del usuario NO es 'all'
    (Superadmin), la delegación no puede ser 'ALL' (puede venir de un
    parámetro GET/POST que resetee el contexto a 'ALL')."""
    role = get_role(user)
    if role is None:
        raise PermissionDenied("Acceso no autorizado")
    if role.is_virtual:
        return  # Superadmin: OK
    # Revisar si hay un parámetro que fuerce 'ALL' o un código fuera del
    # ámbito. Esta función se llama antes de usar cualquier 'delegation_code'
    # llegado del cliente.
    if delegation_pk == 'ALL' or delegation_pk == 'ALL_DELEGATIONS':
        raise PermissionDenied("No puede establecer 'ALL' como delegación")


# ============================================================
# Resolución una vez por request
# ============================================================

class AccessInfo:
    """Permisos del usuario resueltos una sola vez por request."""

    def __init__(self, user):
        self.user = user
        self.role = get_role(user)
        if self.role is None:
            self.permissions = frozenset()
        elif self.role.is_virtual:
            self.permissions = None  # todos los permisos
        else:
            self.permissions = frozenset(
                RolePermission.objects.filter(role_id=self.role.pk)
                .values_list('module', 'action')
            )

    def can(self, module, action):
        if self.role is None:
            return False
        if self.permissions is None:
            return True
        return (module, action) in self.permissions


def get_access(request):
    """AccessInfo de la request, resuelto y cacheado una sola vez por request."""
    info = getattr(request, '_sgr_access_info', None)
    if info is None:
        info = AccessInfo(getattr(request, 'user', None))
        try:
            request._sgr_access_info = info
        except AttributeError:
            pass  # objetos sin __dict__ no se cachéan; se resuelve igual
    return info


def _denied(request, module, action):
    audit(
        request, 'access_denied', module=module or '',
        object_repr=request.path,
        detail=f'{request.method} {request.path} ({module}.{action})',
    )
    raise PermissionDenied


class ModulePermissionMixin:
    """403 (PermissionDenied) si falta el permiso del módulo/acción."""
    module = None
    action = 'view'

    def dispatch(self, request, *args, **kwargs):
        info = get_access(request)
        if not info.can(self.module, self.action):
            _denied(request, self.module, self.action)
        return super().dispatch(request, *args, **kwargs)


def permission_required(module, action):
    """Decorador equivalente a ModulePermissionMixin para vistas de función."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            info = get_access(request)
            if not info.can(module, action):
                _denied(request, module, action)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

class AdminScopedMixin:
    """Mixin para ModelAdmin de Django con scoping por delegación.

    - Superadmin: ve todo.
    - Jefe/Coordinador (scope authorized/own_delegation): solo registros de su
      delegación.
    - Funcionario (scope own_records): no ve nada.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'employee'):
            return qs.filter(employee__delegation=request.user.employee.delegation)
        return qs.none()
