"""Configuración del mantenedor de Tipo de Atención (Parte 6).

Solo lo declara: el motor (``portal.crud.views``) hace todo el trabajo. Un tipo
con sub atenciones o con atenciones no se elimina: se sugiere marcarlo como
Inactivo desde Editar. Bloque 2A: código automático (TAT01...) y orden por
columna.
"""

from django.db.models import Exists, OuterRef

from operaciones.models import Attention
from sgr_core.models import AttentionSubtype, AttentionType

from .config import CELL_STATUS, ColumnSpec, FilterSpec, ModuleConfig, register_module
from .forms import AttentionTypeForm


def subtype_options(request):
    return (
        ("con", "Con sub atenciones"),
        ("sin", "Sin sub atenciones"),
    )


def filter_by_subtypes(queryset, value):
    has_subtypes = Exists(
        AttentionSubtype.alive.filter(attention_type=OuterRef("pk")),
    )
    return queryset.annotate(_has_subtypes=has_subtypes).filter(
        _has_subtypes=(value == "con"),
    )


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
    filters=(
        FilterSpec(
            "subatenciones", "Sub atenciones", "", options=subtype_options,
            apply=filter_by_subtypes,
        ),
    ),
    ordering=("code",),
    default_sort="codigo",
    delete_guard=attention_type_delete_guard,
)

register_module(ATTENTION_TYPES_MODULE)
