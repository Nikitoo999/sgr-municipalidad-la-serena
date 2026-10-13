"""Configuración declarativa de los módulos del CRUD (Parte 4).

Cada mantenedor se declara una sola vez con :class:`ModuleConfig` y se registra
con :func:`register_module`. Las vistas del motor leen esta configuración: el
módulo concreto no duplica lógica en las vistas ni en las plantillas.
"""

from dataclasses import dataclass, field

# Tipos de celda soportados por el listado (se resuelven en la plantilla).
CELL_TEXT = "text"                    # texto plano
CELL_STATUS = "status"                # insignia Activo/Inactivo
CELL_DELEGATION = "delegation_chip"   # chips con color de apoyo de delegación

#: Opciones por defecto del filtro de estado.
DEFAULT_STATUS_OPTIONS = (("Activa", "Activa"), ("Inactiva", "Inactiva"))


@dataclass(frozen=True)
class ColumnSpec:
    """Una columna del listado (y de la exportación).

    - ``field_name``: campo o propiedad del modelo.
    - ``header``: encabezado para el usuario (es-cl).
    - ``cell``: tipo de celda (``CELL_TEXT``, ``CELL_STATUS`` o
      ``CELL_DELEGATION``).
    """

    field_name: str
    header: str
    cell: str = CELL_TEXT
    export: bool = True


@dataclass(frozen=True)
class ModuleConfig:
    """Declaración completa de un módulo del motor CRUD."""

    #: Clave del módulo en la matriz de permisos (delegations, users, ...).
    module_key: str
    #: Segmento de la URL (delegaciones/, usuarios/, ...).
    slug: str
    #: Modelo del CRUD.
    model: type
    #: Formulario del módulo.
    form_class: type
    #: Títulos para el usuario.
    list_title: str
    singular_label: str
    #: Columnas del listado y de la exportación (``export`` decide si van al
    #: Excel; nunca exportar columnas con datos sensibles).
    columns: tuple = ()
    #: Campos donde buscar (varias palabras, todas deben coincidir).
    search_fields: tuple = ()
    #: Campo de estado y sus opciones (para el filtro y las insignias).
    status_field: str | None = None
    status_options: tuple = DEFAULT_STATUS_OPTIONS
    #: Orden por defecto del queryset.
    ordering: tuple = ()
    #: Filas por página del paginador.
    per_page: int = 5
    #: Regla de eliminación: recibe el registro (y el request) y devuelve un
    #: mensaje si hay relaciones que lo bloquean (o cadena vacía si se puede
    #: borrar).
    delete_guard: object = None
    #: Alcance del queryset por usuario/delegación activa. Recibe
    #: ``(request, queryset)`` y devuelve el queryset acotado.
    scope: object = None
    #: Plantilla del formulario. Por defecto la del motor; un módulo puede
    #: aportar la suya (que herede de ``portal/crud/form.html``).
    form_template: str = "portal/crud/form.html"

    @property
    def export_columns(self):
        return tuple(col for col in self.columns if col.export)


_REGISTRY: dict[str, ModuleConfig] = {}


def register_module(config: ModuleConfig) -> None:
    """Registra (o reemplaza) la configuración de un módulo."""
    if not config.module_key or not config.slug:
        raise ValueError("El módulo necesita module_key y slug.")
    _REGISTRY[config.module_key] = config


def get_module(module_key: str) -> ModuleConfig:
    """Configuración de un módulo registrado o ValueError."""
    try:
        return _REGISTRY[module_key]
    except KeyError as exc:
        raise ValueError(f"Módulo CRUD no registrado: {module_key!r}") from exc


def registered_modules() -> tuple:
    """Todos los módulos registrados, en orden de declaración."""
    return tuple(_REGISTRY.values())
