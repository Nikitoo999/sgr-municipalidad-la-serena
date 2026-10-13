"""Rutas del motor CRUD (Parte 4).

Se generan por cada módulo registrado en :mod:`portal.crud.config`:

- ``/<slug>/`` (listado, name = clave del módulo)
- ``/<slug>/nuevo/`` (crear)
- ``/<slug>/<pk>/`` (consultar)
- ``/<slug>/<pk>/editar/`` (editar)
- ``/<slug>/<pk>/eliminar/`` (eliminar, solo POST)
- ``/<slug>/exportar/`` (exportar a Excel)
"""

from django.urls import path

from . import delegations  # noqa: F401  (registra el módulo al importar)
from . import roles  # noqa: F401  (registra el módulo al importar)
from . import users  # noqa: F401  (registra el módulo al importar)
from . import items  # noqa: F401  (registra el módulo al importar)
from . import attention_types  # noqa: F401  (registra el módulo al importar)
from . import attention_subtypes  # noqa: F401  (registra el módulo al importar)
from . import attentions  # noqa: F401  (registra el módulo al importar)
from .attentions import (
    AttentionCreateView,
    AttentionDetailView,
    AttentionExportView,
    AttentionListView,
    AttentionNeighborsView,
    AttentionUpdateView,
)
from .config import registered_modules
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
