"""Configuración del mantenedor de Tipo de Atención (Parte 6).

Solo lo declara: el motor (``portal.crud.views``) hace todo el trabajo. Un tipo
con sub atenciones o con atenciones no se elimina: se sugiere marcarlo como
Inactivo desde Editar.
"""

from operaciones.models import Attention
from sgr_core.models import AttentionType

from .config import CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import AttentionTypeForm


def attention_type_delete_guard(attention_type, request=None):
    """Bloquea el borrado si el tipo tiene sub atenciones o atenciones asociadas."""
    subtypes = attention_type.subtypes.count()
    attentions = Attention.objects.filter(attention_type=attention_type).count()
    parts = []
    if subtypes:
        parts.append(f"{subtypes} sub atención(es)")
    if attentions:
        parts.append(f"{attentions} atención(es)")
    if parts:
        return (
            f"No se puede eliminar el tipo {attention_type.name} porque tiene "
            f"{' y '.join(parts)} asociadas. Márcalo como Inactivo desde Editar "
            f"para conservar el historial."
        )
    return ""


ATTENTION_TYPES_MODULE = ModuleConfig(
    module_key="attention_types",
    slug="tipos-atencion",
    model=AttentionType,
    form_class=AttentionTypeForm,
    list_title="Tipos de atención",
    singular_label="Tipo de atención",
    new_label="Nuevo tipo de atención",
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
    delete_guard=attention_type_delete_guard,
)

register_module(ATTENTION_TYPES_MODULE)
