"""Configuración del mantenedor de Roles (Parte 5).

Solo la declara: el motor (``portal.crud.views``) hace todo el trabajo.
Bloque 2A: código automático (ROL01...), orden por columna (incluida la
cantidad de módulos habilitados) y filtro propio por Alcance.
"""

from django.db.models import Count

from operaciones.models import Employee
from sgr_core.models import Role
from sgr_core.roles import SCOPES

from .config import CELL_STATUS, ColumnSpec, FilterSpec, ModuleConfig, register_module
from .forms import RoleForm


def role_delete_guard(role, request=None):
    """Bloquea el borrado si el rol es del sistema o tiene usuarios asignados.

    Devuelve el mensaje a mostrar o cadena vacía si se puede eliminar. El
    mensaje nunca sugiere desactivar: sugiere reasignar los usuarios.
    """
    if role.is_system:
        return (
            f"No se puede eliminar el rol {role.name}: es el perfil base del "
            f"sistema y solo se puede consultar."
        )
    users = Employee.objects.filter(role=role).count()
    if users:
        return (
            f"No se puede eliminar el rol {role.name} porque tiene {users} "
            f"usuario(s) asignado(s). Reasínalos a otro perfil antes de eliminarlo."
        )
    return ""


def scope_options(request):
    """Alcances de datos (filtro propio "Alcance")."""
    return list(SCOPES)


def role_sort_annotate(queryset, key):
    """La columna "Módulos habilitados" se ordena por un conteo en la BD."""
    if key == "modulos":
        return queryset.annotate(_modulos=Count("permissions__module", distinct=True))
    return queryset


ROLES_MODULE = ModuleConfig(
    module_key="roles",
    slug="roles",
    model=Role,
    form_class=RoleForm,
    list_title="Roles",
    singular_label="Rol",
    gender="m",
    columns=(
        ColumnSpec("code", "Código", sort_key="codigo", sort_fields=("code",)),
        ColumnSpec("name", "Rol", sort_key="nombre", sort_fields=("name",)),
        # El código del alcance ordena de mayor a menor alcance
        # (all, authorized, own_delegation, own_records).
        ColumnSpec("scope_label", "Alcance", sort_key="alcance", sort_fields=("scope",)),
        ColumnSpec("enabled_modules_count", "Módulos habilitados",
                   sort_key="modulos", sort_fields=("_modulos",)),
        ColumnSpec("status", "Estado", cell=CELL_STATUS,
                   sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("code", "name", "scope"),
    search_placeholder="Buscar por código o nombre del rol...",
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    filters=(
        FilterSpec("alcance", "Alcance", "scope", options=scope_options),
    ),
    ordering=("code",),
    default_sort="codigo",
    sort_annotate=role_sort_annotate,
    delete_guard=role_delete_guard,
)

register_module(ROLES_MODULE)
