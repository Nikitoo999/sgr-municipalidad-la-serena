"""Etiqueta de iconos SVG (trazos exactos del bloque ``IC`` de la referencia).

Uso: ``{% load sgr_icons %}{% sgr_icon 'home' 18 %}``.
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Trazos copiados de "docs/diseno/sgr_interfaz_referencia (2).html" (IC).
ICONS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "building": '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17" cy="9" r="2.4"/><path d="M17 14.5c2.4 0 4 1.6 4 4"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 4h12l-2 4 2 4H5"/>',
    "tag": '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.2"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "clip": '<rect x="6" y="4" width="12" height="17" rx="1.5"/><path d="M9 4V3h6v1M9 10h6M9 14h6"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M16 16l5 5"/>',
    "down": '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="1.5"/><path d="M8 11V8a4 4 0 018 0v3"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "alert": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.1"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "pencil": '<path d="M4 20l1-4L16.5 4.5a2 2 0 013 3L8 19l-4 1z"/><path d="M14 7l3 3"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "out": '<path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9"/>',
}


@register.simple_tag
def sgr_icon(name, size=18):
    """Devuelve el SVG del icono ``name`` (desconocido → cadena vacía)."""
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 18
    paths = ICONS.get(name)
    if not paths:
        return ""
    return mark_safe(
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{paths}</svg>"
    )
