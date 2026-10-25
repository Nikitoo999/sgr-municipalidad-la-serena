"""Configuración del mantenedor de Ítems y metas (Parte 6).

Solo lo declara: el motor (``portal.crud.views``) hace todo el trabajo. Los
ítems no tienen relaciones entrantes, así que se borran de forma lógica sin
guard adicional.
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
    new_label="Nuevo ítem",
    columns=(
        ColumnSpec("code", "Código"),
        ColumnSpec("name", "Nombre"),
        ColumnSpec("description", "Descripción"),
        ColumnSpec("status", "Estado", cell=CELL_STATUS),
    ),
    search_fields=("code", "name", "description"),
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    ordering=("code",),
)

register_module(ITEMS_MODULE)
