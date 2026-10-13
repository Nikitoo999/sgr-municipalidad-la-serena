"""Búsqueda inteligente del listado (Parte 4).

Varias palabras, todas deben coincidir en alguno de los campos configurados,
sin distinguir mayúsculas ni tildes:

- MariaDB/MySQL con utf8mb4: la collation (p. ej. utf8mb4_unicode_ci) ya ignora
  tildes y mayúsculas, así que se resuelve con ``icontains`` en el servidor.
- SQLite (desarrollo): normalización simple en Python sobre los valores del
  modelo (sin diacríticos, minúsculas).
"""

import unicodedata

from django.db import connection


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


def _field_values(obj, search_fields) -> str:
    return " ".join(
        normalize(getattr(obj, name, "") or "") for name in search_fields
    )


def apply_search(queryset, search_fields, query):
    """Aplica la búsqueda al queryset (o a la lista de resultados).

    Devuelve un queryset en MariaDB/MySQL y una lista en SQLite (misma
    interfaz de secuencia para el paginador y la exportación).
    """
    terms = split_terms(query)
    if not terms:
        return queryset
    if connection.vendor == "sqlite":
        return [
            obj for obj in queryset
            if all(
                term in _field_values(obj, search_fields) for term in terms
            )
        ]
    # MariaDB: icontains aprovecha la collation insensible a tildes/mayúsculas.
    from django.db.models import Q

    combined = Q()
    for term in terms:
        or_query = Q()
        for name in search_fields:
            or_query |= Q(**{f"{name}__icontains": term})
        combined &= or_query
    return queryset.filter(combined)
