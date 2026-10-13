"""Validadores reutilizables del portal.

RUT chileno: formato y dígito verificador (módulo 11, K = 10). La normalización
de salida siempre es ``12.345.678-5`` (cuerpo con puntos cada tres desde la
derecha, guion y dígito verificador en mayúscula).
"""

import re

from django.core.exceptions import ValidationError

#: Cuerpo (1 a 9 dígitos) + dígito verificador (0-9 o K), con puntos/guion opcionales.
_RUT_INPUT = re.compile(r"^0*(\d{1,9})\s*-?\s*-?([\dKk])$")


def normalize_rut(value):
    """Separa el RUT en ``(cuerpo, dv)`` normalizados, o ``(None, None)``.

    Acepta con y sin puntos, con y sin guion y con K minúscula. No valida el
    dígito verificador: solo el formato.
    """
    text = re.sub(r"[.\s]", "", str(value or ""))
    match = _RUT_INPUT.match(text)
    if match is None:
        return None, None
    body, dv = match.group(1), match.group(2).upper()
    if not body or int(body) == 0:
        return None, None
    return body, dv


def rut_check_digit(body):
    """Dígito verificador de un cuerpo de RUT por el algoritmo módulo 11."""
    total = 0
    multiplier = 2
    for char in reversed(body):
        total += int(char) * multiplier
        multiplier = 2 if multiplier >= 7 else multiplier + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def format_rut(body, dv):
    """Formato canónico del RUT: ``12.345.678-5``."""
    groups = []
    while len(body) > 3:
        groups.insert(0, body[-3:])
        body = body[:-3]
    groups.insert(0, body)
    return f"{'.'.join(groups)}-{dv}"


def validate_rut(value):
    """Valida formato y dígito verificador; devuelve el RUT normalizado.

    Lanza ``ValidationError`` si el formato no calza o si el dígito verificador
    no coincide.
    """
    body, dv = normalize_rut(value)
    if body is None:
        raise ValidationError(
            "Ingresa un RUT válido, por ejemplo 12.345.678-5.",
            code="rut_formato",
        )
    expected = rut_check_digit(body)
    if expected != dv:
        raise ValidationError(
            f"El RUT no es válido: el dígito verificador debería ser {expected}.",
            code="rut_dv",
        )
    return format_rut(body, dv)
