"""Registro de módulos del portal (Parte 3: template común e Inicio).

Deriva el orden y las etiquetas desde ``sgr_core.roles.MODULES`` (claves en
inglés) y asocia cada módulo con su icono exacto de la referencia visual
(``docs/diseno/sgr_interfaz_referencia (2).html``, bloque ``IC``).
"""

MODULE_ORDER = (
    "delegations",
    "roles",
    "users",
    "items",
    "attention_types",
    "attention_subtypes",
    "attentions",
)

MODULE_LABELS = {
    "delegations": "Delegaciones",
    "roles": "Roles",
    "users": "Usuarios",
    "items": "Ítems y metas",
    "attention_types": "Tipo de Atención",
    "attention_subtypes": "Sub Atención",
    "attentions": "Atenciones",
}

MODULE_DESCRIPTIONS = {
    "delegations": "Zonas de atención y su estado.",
    "roles": "Perfiles, alcance y permisos por módulo.",
    "users": "Cuentas, roles y delegaciones autorizadas.",
    "items": "Catálogo de ítems y metas del proyecto.",
    "attention_types": "Clasificación principal de las atenciones.",
    "attention_subtypes": "Detalle de cada tipo de atención.",
    "attentions": "Registro y seguimiento de solicitudes de vecinos.",
}

# Iconos exactos de la referencia: Inicio=home, Delegaciones=building,
# Roles=shield, Usuarios=users, Ítems y metas=flag, Tipo de Atención=tag,
# Sub Atención=layers, Atenciones=clip.
MODULE_ICONS = {
    "home": "home",
    "delegations": "building",
    "roles": "shield",
    "users": "users",
    "items": "flag",
    "attention_types": "tag",
    "attention_subtypes": "layers",
    "attentions": "clip",
}

#: URL names de los placeholders "en construcción" (Partes 4 a 7).
MODULE_URL_NAMES = {
    "delegations": "delegations",
    "roles": "roles",
    "users": "users",
    "items": "items",
    "attention_types": "attention_types",
    "attention_subtypes": "attention_subtypes",
    "attentions": "attentions",
}
