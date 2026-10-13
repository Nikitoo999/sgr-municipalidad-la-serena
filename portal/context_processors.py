"""Contexto común del portal (Parte 3: template común e Inicio).

Expone en cada render: acceso resuelto una vez por request, delegaciones
permitidas/activa, colores ``--dc``/``--dm`` de la insignia y menú filtrado
por permiso ``view``. Réplica en Python ``readable``/``mixWhite`` de
"docs/diseno/sgr_interfaz_referencia (2).html".
"""
from django.contrib.messages import get_messages

from . import access
from .modules import MODULE_DESCRIPTIONS, MODULE_ICONS, MODULE_LABELS, MODULE_ORDER, MODULE_URL_NAMES

#: Color institucional (insignia "todas" y respaldo sin color de delegación).
INSTITUTIONAL_COLOR = "#920000"


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(v))) for v in rgb))


def _luminance(rgb):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable(hex_color, steps=24):
    """Oscurece ×0,94 por paso hasta contraste 4,5:1 contra blanco."""
    rgb = list(_hex_to_rgb(hex_color))
    for _ in range(steps):
        if 1.05 / (_luminance(rgb) + 0.05) >= 4.5:
            break
        rgb = [v * 0.94 for v in rgb]
    return _rgb_to_hex(rgb)


def mix_white(hex_color, proportion=0.55):
    """Mezcla el color con blanco en la proporción indicada."""
    return _rgb_to_hex([v + (255 - v) * proportion for v in _hex_to_rgb(hex_color)])


def badge_colors(base_color):
    """Devuelve ``(--dc, --dm)`` para la insignia de delegación."""
    base = (base_color or "").strip() or INSTITUTIONAL_COLOR
    if not base.startswith("#") or len(base) != 7:
        base = INSTITUTIONAL_COLOR
    try:
        return readable(base), mix_white(base, 0.55)
    except (ValueError, TypeError):
        return INSTITUTIONAL_COLOR, mix_white(INSTITUTIONAL_COLOR, 0.55)


def sgr_context(request):
    """Variables comunes del shell (cabecera, menú, delegación activa)."""
    info = access.get_access(request)
    allowed = access.allowed_delegations(request.user)
    active = access.get_active_delegation(request)
    is_all = active == access.ALL_DELEGATIONS

    if is_all:
        active_code = "ALL"
        active_name = "Todas las delegaciones"
        base_color = INSTITUTIONAL_COLOR
    elif active is not None:
        active_code = active.code
        active_name = f"{active.code} | Delegación {active.name}"
        base_color = active.color or INSTITUTIONAL_COLOR
    else:
        active_code = ""
        active_name = ""
        base_color = INSTITUTIONAL_COLOR

    dc, dm = badge_colors(base_color)
    can_switch = len(allowed) > 1 or (info.role is not None and info.role.scope == "all")

    menu = [
        {
            "key": module,
            "label": MODULE_LABELS[module],
            "description": MODULE_DESCRIPTIONS[module],
            "icon": MODULE_ICONS[module],
            "url_name": MODULE_URL_NAMES[module],
        }
        for module in MODULE_ORDER
        if info.can(module, "view")
    ]

    if getattr(request.user, "is_authenticated", False):
        display_name = request.user.get_full_name() or request.user.username
    else:
        display_name = ""
    initials = "".join(w[0] for w in display_name.split()[:2]).upper()

    # Mensajes serializados en el servidor: el template los inyecta con
    # ``json_script`` (JSON válido fuera del <script> de ejecución), así el
    # validador del editor no los marca como errores de JavaScript.
    storage = get_messages(request)
    flashed = [
        {"tags": message.tags, "text": str(message.message)}
        for message in storage
    ]

    return {
        "sgr_access": info,
        "sgr_role": info.role,
        "sgr_allowed_delegations": allowed,
        "sgr_active_delegation": active,
        "sgr_active_is_all": is_all,
        "sgr_active_code": active_code,
        "sgr_active_name": active_name,
        "sgr_badge_dc": dc,
        "sgr_badge_dm": dm,
        "sgr_can_switch_delegation": can_switch,
        "sgr_menu": menu,
        "sgr_display_name": display_name,
        "sgr_initials": initials,
        "sgr_messages": flashed,
    }
