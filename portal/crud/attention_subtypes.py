"""Configuración del mantenedor de Sub Atención (Parte 6).

Solo lo declara: el motor (``portal.crud.views``) hace todo el trabajo. Una sub
atención con atenciones asociadas no se elimina: se sugiere marcarla como
Inactiva desde Editar. Bloque 2A: código automático (SAT001...), orden por
columna y filtro propio por Tipo de atención.
"""

from operaciones.models import Attention
from sgr_core.models import AttentionSubtype, AttentionType

from .config import CELL_STATUS, ColumnSpec, FilterSpec, ModuleConfig, register_module
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


def type_options(request):
    """Tipos de atención vivos (filtro propio "Tipo de atención")."""
    return [
        (item.pk, f"{item.code} · {item.name}" + ("" if item.status == "Activo" else " (inactivo)"))
        for item in AttentionType.alive.order_by("code")
    ]


ATTENTION_SUBTYPES_MODULE = ModuleConfig(
    module_key="attention_subtypes",
    slug="sub-atenciones",
    model=AttentionSubtype,
    form_class=AttentionSubtypeForm,
    list_title="Sub atenciones",
    singular_label="Sub atención",
    gender="f",
    columns=(
        ColumnSpec("code", "Código", sort_key="codigo", sort_fields=("code",)),
        ColumnSpec("name", "Nombre", sort_key="nombre", sort_fields=("name",)),
        ColumnSpec("attention_type", "Tipo asociado",
                   sort_key="tipo", sort_fields=("attention_type__code",)),
        ColumnSpec("status", "Estado", cell=CELL_STATUS,
                   sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("code", "name", "attention_type__name", "attention_type__code"),
    search_placeholder="Buscar por código, nombre o tipo de atención...",
    status_field="status",
    status_options=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
    filters=(
        FilterSpec("tipo", "Tipo de atención", "attention_type_id", options=type_options),
    ),
    ordering=("code",),
    default_sort="codigo",
    select_related=("attention_type",),
    delete_guard=attention_subtype_delete_guard,
)

register_module(ATTENTION_SUBTYPES_MODULE)
