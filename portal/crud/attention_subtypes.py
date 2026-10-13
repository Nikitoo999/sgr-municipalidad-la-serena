"""Configuración del mantenedor de Sub Atención (Parte 6).

Solo lo declara: el motor (``portal.crud.views``) hace todo el trabajo. Una sub
atención con atenciones asociadas no se elimina: se sugiere marcarla como
Inactiva desde Editar.
"""

from operaciones.models import Attention
from sgr_core.models import AttentionSubtype

from .config import CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import AttentionSubtypeForm


def attention_subtype_delete_guard(attention_subtype, request=None):
    """Bloquea el borrado si la sub atención tiene atenciones asociadas."""
    attentions = Attention.objects.filter(attention_subtype=attention_subtype).count()
    if attentions:
        return (
            f"No se puede eliminar la sub atención {attention_subtype.name} porque "
            f"tiene {attentions} atención(es) asociadas. Márcala como Inactiva "
            f"desde Editar para conservar el historial."
        )
    return ""


ATTENTION_SUBTYPES_MODULE = ModuleConfig(
    module_key="attention_subtypes",
    slug="sub-atenciones",
    model=AttentionSubtype,
    form_class=AttentionSubtypeForm,
    list_title="Sub atenciones",
    singular_label="Sub atención",
    columns=(
        ColumnSpec("code", "Código"),
        ColumnSpec("name", "Nombre"),
        ColumnSpec("attention_type", "Tipo asociado"),
        ColumnSpec("status", "Estado", cell=CELL_STATUS),
    ),
    search_fields=("code", "name", "attention_type__name", "attention_type__code"),
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    ordering=("code",),
    delete_guard=attention_subtype_delete_guard,
)

register_module(ATTENTION_SUBTYPES_MODULE)
