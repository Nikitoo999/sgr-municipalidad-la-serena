"""Configuración del mantenedor de Delegaciones (Parte 4).

Solo la declara: el motor (``portal.crud.views``) hace todo el trabajo.
"""

from operaciones.models import Attention, Employee
from sgr_core.models import Delegation, InstitutionalGoal

from .config import CELL_STATUS, ColumnSpec, ModuleConfig, register_module
from .forms import DelegationForm


def delegation_delete_guard(delegation):
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


DELEGATIONS_MODULE = ModuleConfig(
    module_key="delegations",
    slug="delegaciones",
    model=Delegation,
    form_class=DelegationForm,
    list_title="Delegaciones",
    singular_label="Delegación",
    columns=(
        ColumnSpec("code", "Código"),
        ColumnSpec("name", "Nombre"),
        ColumnSpec("commune", "Comuna"),
        ColumnSpec("address", "Dirección"),
        ColumnSpec("status", "Estado", cell=CELL_STATUS),
    ),
    search_fields=("code", "name", "commune", "address"),
    status_field="status",
    ordering=("code",),
    delete_guard=delegation_delete_guard,
)

register_module(DELEGATIONS_MODULE)
