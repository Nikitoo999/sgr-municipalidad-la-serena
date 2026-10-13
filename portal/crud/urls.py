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
from .config import registered_modules
from .views import (
    CrudCreateView,
    CrudDeleteView,
    CrudDetailView,
    CrudExportView,
    CrudListView,
    CrudUpdateView,
)


def _module_paths(config):
    key = config.module_key
    return [
        path(
            f"{config.slug}/",
            CrudListView.as_view(module_key=key),
            name=key,
        ),
        path(
            f"{config.slug}/nuevo/",
            CrudCreateView.as_view(module_key=key),
            name=f"{key}_new",
        ),
        path(
            f"{config.slug}/<int:pk>/",
            CrudDetailView.as_view(module_key=key),
            name=f"{key}_detail",
        ),
        path(
            f"{config.slug}/<int:pk>/editar/",
            CrudUpdateView.as_view(module_key=key),
            name=f"{key}_edit",
        ),
        path(
            f"{config.slug}/<int:pk>/eliminar/",
            CrudDeleteView.as_view(module_key=key),
            name=f"{key}_delete",
        ),
        path(
            f"{config.slug}/exportar/",
            CrudExportView.as_view(module_key=key),
            name=f"{key}_export",
        ),
    ]


urlpatterns = [
    route
    for config in registered_modules()
    for route in _module_paths(config)
]
