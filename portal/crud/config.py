"""Configuración declarativa de los módulos del CRUD (Parte 4).

Cada mantenedor se declara una sola vez con :class:`ModuleConfig` y se registra
con :func:`register_module`. Las vistas del motor leen esta configuración: el
módulo concreto no duplica lógica en las vistas ni en las plantillas.

Bloque 2A: la configuración también declara el género del nombre (para los
títulos propios "Nuevo usuario", "Nueva delegación"...), el orden por columna
(``ColumnSpec.sort_key``), los filtros propios de cada tabla
(:class:`FilterSpec`) y los tamaños de página permitidos.
"""

from dataclasses import dataclass

# Tipos de celda soportados por el listado (se resuelven en la plantilla).
CELL_TEXT = "text"                    # texto plano
CELL_STATUS = "status"                # insignia Activo/Inactivo
CELL_DELEGATION = "delegation_chip"   # chips con color de apoyo de delegación

#: Opciones por defecto del filtro de estado.
DEFAULT_STATUS_OPTIONS = (("Activa", "Activa"), ("Inactiva", "Inactiva"))

#: Filas por página de los mantenedores (el primero es el valor por defecto).
DEFAULT_PAGE_SIZE_OPTIONS = (5, 15, 30)

#: Participios de los mensajes de éxito según la acción.
_PARTICIPLES = {"create": "cread", "edit": "actualizad", "delete": "eliminad"}


@dataclass(frozen=True)
class ColumnSpec:
    """Una columna del listado (y de la exportación).

    - ``field_name``: campo o propiedad del modelo.
    - ``header``: encabezado para el usuario (es-cl).
    - ``cell``: tipo de celda (``CELL_TEXT``, ``CELL_STATUS`` o
      ``CELL_DELEGATION``).
    - ``sort_key``: clave pública de orden (``?orden=<clave>`` ascendente,
      ``?orden=-<clave>`` descendente). Vacía = la columna no se ordena.
    - ``sort_fields``: campos reales del ORM para ese orden (un ``-`` inicial
      invierte el sentido de ese campo).
    """

    field_name: str
    header: str
    cell: str = CELL_TEXT
    export: bool = True
    sort_key: str = ""
    sort_fields: tuple = ()


@dataclass(frozen=True)
class FilterSpec:
    """Filtro propio de una tabla (un selector en la barra de búsqueda).

    - ``param``: nombre del parámetro GET (``rol``, ``delegacion``, ``tipo``...).
    - ``label``: etiqueta del selector.
    - ``lookup``: campo del ORM que se filtra (``role_id``, ``scope``...).
    - ``options``: función ``(request) -> [(valor, etiqueta), ...]``. Solo se
      aplica un valor que esté en esta lista blanca: un parámetro manipulado se
      ignora y nunca amplía el alcance del usuario.
    - ``apply``: función opcional ``(queryset, valor) -> queryset`` para
      filtros que no son un ``filter(lookup=valor)`` directo.
    - ``empty_label``: texto de la opción que no filtra.
    """

    param: str
    label: str
    lookup: str
    options: object
    apply: object = None
    empty_label: str = "Todos"

    def filter_queryset(self, queryset, value):
        if self.apply is not None:
            return self.apply(queryset, value)
        return queryset.filter(**{self.lookup: value})


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
    #: Género gramatical de ``singular_label``: "m" (el usuario) o "f" (la
    #: delegación). Arma "Nuevo/Nueva ...", "creado/creada", etc.
    gender: str = "m"
    #: Columnas del listado y de la exportación (``export`` decide si van al
    #: Excel; nunca exportar columnas con datos sensibles).
    columns: tuple = ()
    #: Campos donde buscar (varias palabras, todas deben coincidir).
    search_fields: tuple = ()
    #: Texto de ayuda del buscador.
    search_placeholder: str = "Buscar por nombre, código u otro campo..."
    #: Campo de estado y sus opciones (para el filtro y las insignias).
    status_field: str | None = None
    status_options: tuple = DEFAULT_STATUS_OPTIONS
    #: Filtro de estado propio: ``(queryset, valor) -> queryset``. Por defecto
    #: se filtra ``status_field`` por el valor elegido.
    status_filter: object = None
    #: Filtros propios de la tabla (por Rol, Delegación, Tipo...).
    filters: tuple = ()
    #: Orden base del queryset (antes del orden por columna).
    ordering: tuple = ()
    #: Orden por defecto: clave pública de una columna (``-clave`` = desc.).
    default_sort: str = ""
    #: Anotaciones para ordenar por columnas calculadas:
    #: ``(queryset, clave) -> queryset``.
    sort_annotate: object = None
    #: Filas por página permitidas (la primera es la de por defecto).
    page_size_options: tuple = DEFAULT_PAGE_SIZE_OPTIONS
    #: Relaciones que se traen en la misma consulta del listado (evita N+1).
    select_related: tuple = ()
    #: Texto con que se nombra un registro en la confirmación de borrado.
    #: Recibe el objeto; por defecto "código · nombre" o ``str(obj)``.
    row_label: object = None
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

    # ------------------------------------------------------------------
    # Columnas y orden
    # ------------------------------------------------------------------

    @property
    def export_columns(self):
        return tuple(col for col in self.columns if col.export)

    @property
    def sort_map(self):
        """``{clave_publica: campos_orm}`` de las columnas ordenables."""
        return {
            column.sort_key: tuple(column.sort_fields)
            for column in self.columns
            if column.sort_key and column.sort_fields
        }

    @property
    def per_page(self):
        """Filas por página por defecto (compatibilidad con la Parte 4)."""
        return self.page_size_options[0]

    # ------------------------------------------------------------------
    # Textos con nombre propio (Bloque 2A)
    # ------------------------------------------------------------------

    @property
    def is_feminine(self):
        return self.gender == "f"

    @property
    def noun(self):
        """Nombre singular para usar dentro de una frase ("delegación")."""
        return self.singular_label[:1].lower() + self.singular_label[1:]

    @property
    def article(self):
        """Artículo definido del nombre: "el" usuario / "la" delegación."""
        return "la" if self.is_feminine else "el"

    @property
    def new_title(self):
        """"Nuevo usuario", "Nueva delegación", "Nuevo ítem"..."""
        return f"{'Nueva' if self.is_feminine else 'Nuevo'} {self.noun}"

    @property
    def edit_title(self):
        """"Editar usuario", "Editar delegación"..."""
        return f"Editar {self.noun}"

    @property
    def view_title(self):
        """"Consulta de usuario", "Consulta de delegación"..."""
        return f"Consulta de {self.noun}"

    @property
    def save_label(self):
        """Texto del botón al crear: "Guardar usuario", "Guardar delegación"."""
        return f"Guardar {self.noun}"

    def page_title(self, mode):
        """Título propio según el modo del formulario (create/edit/view)."""
        return {
            "create": self.new_title,
            "edit": self.edit_title,
            "view": self.view_title,
        }.get(mode, self.list_title)

    def success_message(self, action):
        """"Usuario creado correctamente.", "Delegación eliminada correctamente."."""
        ending = "a" if self.is_feminine else "o"
        participle = _PARTICIPLES.get(action, "guardad")
        return f"{self.singular_label} {participle}{ending} correctamente."

    @property
    def delete_text(self):
        """Texto del modal de borrado con el género correcto."""
        ending = "a" if self.is_feminine else "o"
        return (
            f"{self.article.capitalize()} {self.noun} se marcará como eliminad{ending} "
            "y dejará de aparecer en las listas. Esta acción queda registrada "
            "en la auditoría."
        )

    def label_for(self, obj):
        """Nombre del registro para la confirmación de borrado y los aria-label."""
        if self.row_label is not None:
            return str(self.row_label(obj))
        code = getattr(obj, "code", "")
        name = getattr(obj, "name", "")
        if code and name:
            return f"{code} · {name}"
        return str(obj)


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
