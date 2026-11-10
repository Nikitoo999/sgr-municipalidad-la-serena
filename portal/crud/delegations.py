"""Configuración del mantenedor de Delegaciones (Parte 4).

Solo la declara: el motor (``portal.crud.views``) hace todo el trabajo.
Bloque 2A: código automático (DEL01...), orden por columna y filtro propio por
Comuna.
"""

from operaciones.models import Attention, Employee
from sgr_core.models import Delegation, InstitutionalGoal

from .config import CELL_STATUS, ColumnSpec, FilterSpec, ModuleConfig, register_module
from .forms import DelegationForm


def delegation_delete_guard(delegation, request=None):
    """Bloquea el borrado si la delegación tiene registros relacionados.

    Devuelve el mensaje a mostrar o cadena vacía si se puede eliminar.
    """
    blockers = []
    employees = Employee.objects.filter(delegation=delegation).count()
    employees += Employee.objects.filter(
        authorized_delegations=delegation
    ).count()
    attentions = Attention.objects.filter(delegation=delegation).count()
    goals = InstitutionalGoal.objects.filter(delegation=delegation).count()

    parts = []
    if employees:
        parts.append(f"{employees} usuario(s)")
    if attentions:
        parts.append(f"{attentions} atención(es)")
    if goals:
        parts.append(f"{goals} meta(s)")
    if parts:
        blockers.append(
            f"No se puede eliminar la delegación {delegation.name} porque tiene "
            f"{' y '.join(parts)} asociados. Márcala como Inactiva desde "
            f"Editar para conservar el historial."
        )
    return " ".join(blockers)


def commune_options(request):
    """Comunas de las delegaciones vivas (filtro propio "Comuna")."""
    communes = (
        Delegation.alive.exclude(commune="")
        .order_by("commune")
        .values_list("commune", flat=True)
        .distinct()
    )
    return [(commune, commune) for commune in communes]


DELEGATIONS_MODULE = ModuleConfig(
    module_key="delegations",
    slug="delegaciones",
    model=Delegation,
    form_class=DelegationForm,
    list_title="Delegaciones",
    singular_label="Delegación",
    gender="f",
    columns=(
        ColumnSpec("code", "Código", sort_key="codigo", sort_fields=("code",)),
        ColumnSpec("name", "Nombre", sort_key="nombre", sort_fields=("name",)),
        ColumnSpec("commune", "Comuna", sort_key="comuna", sort_fields=("commune",)),
        ColumnSpec("address", "Dirección", sort_key="direccion", sort_fields=("address",)),
        ColumnSpec("status", "Estado", cell=CELL_STATUS,
                   sort_key="estado", sort_fields=("status",)),
    ),
    search_fields=("code", "name", "commune", "address"),
    search_placeholder="Buscar por código, nombre, comuna o dirección...",
    status_field="status",
    filters=(
        FilterSpec("comuna", "Comuna", "commune", options=commune_options,
                   empty_label="Todas"),
    ),
    ordering=("code",),
    default_sort="codigo",
    delete_guard=delegation_delete_guard,
)

register_module(DELEGATIONS_MODULE)
