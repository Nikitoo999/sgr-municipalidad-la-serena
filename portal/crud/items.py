"""Configuración del mantenedor de Ítems y metas (Parte 6).

Solo lo declara: el motor (``portal.crud.views``) hace todo el trabajo. Los
ítems no tienen relaciones entrantes, así que se borran de forma lógica sin
guard adicional. Bloque 2A: código automático (ITM001...) y orden por columna.
"""

from sgr_core.models import ProjectItem

from .config import CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import ProjectItemForm


ITEMS_MODULE = ModuleConfig(
    module_key="items",
    slug="items",
    model=ProjectItem,
    form_class=ProjectItemForm,
    list_title="Ítems y metas",
    singular_label="Ítem",
    gender="m",
    columns=(
        ColumnSpec("code", "Código", sort_key="codigo", sort_fields=("code",)),
        ColumnSpec("name", "Nombre", sort_key="nombre", sort_fields=("name",)),
        ColumnSpec("description", "Descripción",
                   sort_key="descripcion", sort_fields=("description",)),
        ColumnSpec("status", "Estado", cell=CELL_STATUS,
                   sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("code", "name", "description"),
    search_placeholder="Buscar por código, nombre o descripción...",
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    ordering=("code",),
    default_sort="codigo",
)

register_module(ITEMS_MODULE)
