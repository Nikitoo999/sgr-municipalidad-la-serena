"""Rutas del motor CRUD (Parte 4).

Se generan por cada módulo registrado en :mod:`portal.crud.config`:

- ``/<slug>/`` (listado, name = clave del módulo)
- ``/<slug>/nuevo/`` (crear)
- ``/<slug>/<pk>/`` (consultar)
- ``/<slug>/<pk>/editar/`` (editar)
- ``/<slug>/<pk>/eliminar/`` (eliminar, solo POST)
- ``/<slug>/exportar/`` (exportar a Excel)

Atenciones (Bloque 2B) suma ``/atenciones/<pk>/gestiones/nueva/`` (gestión de
seguimiento, solo POST) y ``/atenciones/cierre-semanal/`` (cierre semanal).
"""

from django.urls import path

from . import delegations  # noqa: F401  (registra el módulo al importar)
from . import roles  # noqa: F401  (registra el módulo al importar)
from . import users  # noqa: F401  (registra el módulo al importar)
from . import items  # noqa: F401  (registra el módulo al importar)
from . import attention_types  # noqa: F401  (registra el módulo al importar)
from . import attention_subtypes  # noqa: F401  (registra el módulo al importar)
from . import attentions  # noqa: F401  (registra el módulo al importar)
from . import organizations  # noqa: F401  (registra el módulo al importar)
from . import positions  # noqa: F401  (registra el módulo al importar)
from . import periods  # noqa: F401  (registra el módulo al importar)
from .attentions import (
    AttentionCreateView,
    AttentionDetailView,
    AttentionExportView,
    AttentionFollowUpCreateView,
    AttentionListView,
    AttentionNeighborsView,
    AttentionUpdateView,
    AttentionWeekClosureView,
)
from .attention_extras import (
    AttentionCommentCreateView,
    AttentionReviewView,
    AttentionRutCheckView,
    OrganizationLookupView,
    OrganizationMembersView,
)
from .organizations import (
    DirectiveRoleCreateView,
    DirectiveRoleDeleteView,
    DirectiveRoleUpdateView,
    OrganizationChartView,
    OrganizationMemberRemoveView,
    OrganizationMemberSaveView,
)
from .config import registered_modules
from .periods import PeriodCloseView
from .positions import PositionGoalsView
from .views import (
    CrudCreateView,
    CrudDeleteView,
    CrudDetailView,
    CrudExportView,
    CrudListView,
    CrudUpdateView,
)


#: Vistas por módulo que usan una implementación propia (Atenciones, Parte 7).
_CUSTOM_MODULE_VIEWS = {
    "attentions": {
        "list": AttentionListView,
        "create": AttentionCreateView,
        "detail": AttentionDetailView,
        "edit": AttentionUpdateView,
        "export": AttentionExportView,
    },
}


def _module_paths(config):
    key = config.module_key
    custom = _CUSTOM_MODULE_VIEWS.get(key, {})
    list_view = custom.get("list", CrudListView)
    create_view = custom.get("create", CrudCreateView)
    detail_view = custom.get("detail", CrudDetailView)
    edit_view = custom.get("edit", CrudUpdateView)
    export_view = custom.get("export", CrudExportView)
    return [
        path(
            f"{config.slug}/",
            list_view.as_view(module_key=key),
            name=key,
        ),
        path(
            f"{config.slug}/nuevo/",
            create_view.as_view(module_key=key),
            name=f"{key}_new",
        ),
        path(
            f"{config.slug}/<int:pk>/",
            detail_view.as_view(module_key=key),
            name=f"{key}_detail",
        ),
        path(
            f"{config.slug}/<int:pk>/editar/",
            edit_view.as_view(module_key=key),
            name=f"{key}_edit",
        ),
        path(
            f"{config.slug}/<int:pk>/eliminar/",
            CrudDeleteView.as_view(module_key=key),
            name=f"{key}_delete",
        ),
        path(
            f"{config.slug}/exportar/",
            export_view.as_view(module_key=key),
            name=f"{key}_export",
        ),
    ]


urlpatterns = [
    route
    for config in registered_modules()
    for route in _module_paths(config)
]

# Endpoint de búsqueda de solicitantes para el ingreso de atención.
urlpatterns.append(
    path("atenciones/solicitantes/", AttentionNeighborsView.as_view(), name="attention_neighbors"),
)

# Unidad 3: validación del punto, funcionario solicitante, organizaciones y comentarios.
urlpatterns += [
    path("atenciones/funcionario-por-rut/", AttentionRutCheckView.as_view(), name="attention_rut_check"),
    path(
        "atenciones/<int:pk>/validar/",
        AttentionReviewView.as_view(module_key="attentions"),
        name="attention_review",
    ),
    path(
        "atenciones/<int:pk>/comentarios/nuevo/",
        AttentionCommentCreateView.as_view(module_key="attentions"),
        name="attention_comment",
    ),
    path("organizaciones/buscar/", OrganizationLookupView.as_view(), name="organization_lookup"),
    path(
        "organizaciones/organigrama/",
        OrganizationChartView.as_view(module_key="organizations"),
        name="organization_chart",
    ),
    path(
        "organizaciones/cargos-directivos/<int:role_pk>/editar/",
        DirectiveRoleUpdateView.as_view(module_key="organizations"),
        name="directive_role_update",
    ),
    path(
        "organizaciones/cargos-directivos/<int:role_pk>/eliminar/",
        DirectiveRoleDeleteView.as_view(module_key="organizations"),
        name="directive_role_delete",
    ),
    path(
        "organizaciones/<int:pk>/directiva/",
        OrganizationMemberSaveView.as_view(module_key="organizations"),
        name="organization_member_save",
    ),
    path(
        "organizaciones/<int:pk>/directiva/<int:member_pk>/vacante/",
        OrganizationMemberRemoveView.as_view(module_key="organizations"),
        name="organization_member_remove",
    ),
    path(
        "organizaciones/cargos-directivos/nuevo/",
        DirectiveRoleCreateView.as_view(module_key="organizations"),
        name="directive_role_create",
    ),
    path(
        "organizaciones/<int:pk>/directiva.json",
        OrganizationMembersView.as_view(),
        name="organization_members_json",
    ),
]

# Bloque 2B: gestiones de seguimiento y cierre semanal de atenciones.
urlpatterns += [
    path(
        "atenciones/<int:pk>/gestiones/nueva/",
        AttentionFollowUpCreateView.as_view(module_key="attentions"),
        name="attention_follow_up_new",
    ),
    path(
        "atenciones/cierre-semanal/",
        AttentionWeekClosureView.as_view(module_key="attentions"),
        name="attention_week_closures",
    ),
]

# Unidad 3: cierre de trimestre y metas por cargo.
urlpatterns += [
    path("periodos/cierre/", PeriodCloseView.as_view(), name="period_close"),
    path("cargos/<int:pk>/metas/", PositionGoalsView.as_view(), name="position_goals"),
]
