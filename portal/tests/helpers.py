"""Preparación común de las pruebas del CRUD (Parte 5 en adelante).

Solo utilidades: ninguna función empieza por ``test_`` ni contiene aserciones,
así ningún corredor de pruebas las descubre como tests (regla 10). Los archivos
de pruebas concretos definen sus propias clases ``TestCase`` e importan estas
ayudas.
"""

from django.contrib.auth import get_user_model

from operaciones.models import Employee
from sgr_core.models import Delegation, Role, RolePermission
from sgr_core.roles import ensure_base_roles

from .utils import TEST_STORAGES  # noqa: F401  (re-exportado para las pruebas)

User = get_user_model()

DEMO_PASSWORD = "Demo2026!"


def ensure_roles():
    """Crea/actualiza los 4 roles base y devuelve {codigo: Role}."""
    ensure_base_roles(Role, RolePermission)
    return {role.code: role for role in Role.objects.all()}


def make_delegation(name, code, **kwargs):
    """Crea una delegación con valores por defecto razonables."""
    kwargs.setdefault("commune", "La Serena")
    kwargs.setdefault("status", "Activa")
    return Delegation.objects.create(name=name, code=code, **kwargs)


def make_user(username, **kwargs):
    """Usuario con la clave demo (los tests pueden cambiarla con set_password)."""
    kwargs.setdefault("password", DEMO_PASSWORD)
    return User.objects.create_user(username=username, **kwargs)


def make_employee(username, rut, delegation, role, **user_kwargs):
    """Crea User + Employee en un paso (rut único por prueba)."""
    user = make_user(username, **user_kwargs)
    return Employee.objects.create(user=user, rut=rut, delegation=delegation, role=role)


def permission_pairs(role):
    """Conjunto de pares (modulo, accion) asignados a un rol."""
    return set(RolePermission.objects.filter(role=role).values_list("module", "action"))
