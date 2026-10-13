"""Motor de mantenedores del portal (Parte 4).

Componentes reutilizables de todo CRUD (listado, búsqueda, filtro, paginador,
formulario, acciones con iconos, exportación, borrado lógico y auditoría).
Las Partes 5 a 7 solo registran módulos en :mod:`portal.crud.config`.
"""

from .config import (
    ColumnSpec,
    ModuleConfig,
    get_module,
    registered_modules,
    register_module,
)
from .search import apply_search
from .views import (
    CrudCreateView,
    CrudDeleteView,
    CrudDetailView,
    CrudExportView,
    CrudListView,
    CrudUpdateView,
)

__all__ = [
    "ColumnSpec",
    "ModuleConfig",
    "register_module",
    "get_module",
    "registered_modules",
    "apply_search",
    "CrudListView",
    "CrudCreateView",
    "CrudDetailView",
    "CrudUpdateView",
    "CrudDeleteView",
    "CrudExportView",
]
