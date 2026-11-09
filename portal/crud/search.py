"""Búsqueda inteligente del listado (Parte 4, Bloque 2A).

Varias palabras, todas deben coincidir en alguno de los campos configurados,
sin distinguir mayúsculas ni tildes. Siempre devuelve un ``QuerySet``: el
filtro lo resuelve la base de datos y nunca se cargan los registros en una
lista de Python para filtrarlos (así la paginación y la exportación siguen
trabajando con consultas SQL).

- MariaDB/MySQL con utf8mb4: la collation (p. ej. utf8mb4_unicode_ci) ya
  ignora tildes y mayúsculas, así que basta ``icontains``.
- SQLite (desarrollo): SQLite no sabe quitar tildes, así que en cada conexión
  se registra la función SQL ``sgr_normalizar`` (ver
  :func:`register_sqlite_functions`, conectada en ``portal.apps``). La consulta
  queda ``WHERE sgr_normalizar(campo) LIKE '%termino%'``.
"""

import unicodedata

from django.db import connections
from django.db.models import CharField, Func, Q

#: Nombre de la función SQL que se registra en SQLite.
SQLITE_NORMALIZE_FUNCTION = "sgr_normalizar"


def normalize(value) -> str:
    """Minúsculas sin diacríticos (normalización simple, sin dependencias)."""
    text = str(value if value is not None else "")
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


def split_terms(query: str) -> list:
    """Divide la búsqueda en palabras normalizadas no vacías."""
    if not query:
        return []
    return [term for term in normalize(query).split() if term]


def _sqlite_normalize(value):
    """Implementación en Python de ``sgr_normalizar`` (la llama SQLite)."""
    if value is None:
        return ""
    return normalize(value)


def register_sqlite_functions(sender=None, connection=None, **kwargs):
    """Registra ``sgr_normalizar`` en cada conexión SQLite nueva.

    Se conecta a la señal ``connection_created`` en ``PortalConfig.ready``.
    En MariaDB no hace nada (allí la collation resuelve tildes y mayúsculas).
    """
    if connection is None or connection.vendor != "sqlite":
        return
    connection.connection.create_function(
        SQLITE_NORMALIZE_FUNCTION, 1, _sqlite_normalize, deterministic=True,
    )


class Normalize(Func):
    """``sgr_normalizar(campo)``: el valor en minúsculas y sin tildes."""

    function = SQLITE_NORMALIZE_FUNCTION
    output_field = CharField()


def apply_search(queryset, search_fields, query):
    """Aplica la búsqueda al queryset y devuelve otro queryset.

    Cada término debe aparecer en al menos uno de ``search_fields`` (Y entre
    términos, O entre campos). Los campos admiten rutas con ``__``
    (``delegation__name``).
    """
    terms = split_terms(query)
    if not terms or not search_fields:
        return queryset

    if connections[queryset.db].vendor == "sqlite":
        # alias() no agrega columnas al SELECT: solo sirve para filtrar.
        aliases = {
            f"_sgr_busqueda_{index}": Normalize(name)
            for index, name in enumerate(search_fields)
        }
        queryset = queryset.alias(**aliases)
        names, lookup = list(aliases), "contains"
    else:
        names, lookup = list(search_fields), "icontains"

    combined = Q()
    for term in terms:
        any_field = Q()
        for name in names:
            any_field |= Q(**{f"{name}__{lookup}": term})
        combined &= any_field
    return queryset.filter(combined)
