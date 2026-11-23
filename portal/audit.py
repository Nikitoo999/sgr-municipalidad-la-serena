"""Auditoría de accesos y acciones relevantes (RF-036 / RNF-008 / HU-30).

Cada evento guarda usuario, fecha, acción, módulo, objeto, IP y, en las
ediciones, el valor anterior y el nuevo de cada campo modificado (``changes``,
JSON). Nunca se guardan contraseñas, hashes ni tokens.
"""
import json

from django.core.files import File
from django.db.models.fields.files import FieldFile

from .models import AuditLog

#: Fragmentos de nombre de campo que nunca se registran.
SENSITIVE = ("password", "token", "hash", "secret")


def _plain(value):
    """Valor legible y serializable para la auditoría."""
    if value is None:
        return ""
    if hasattr(value, "all") and callable(value.all):
        value = list(value.all())
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_plain(v) for v in value)
    if isinstance(value, (FieldFile, File)):
        # Ojo: ``.url`` de un archivo vacío lanza ValueError; solo se usa el nombre.
        return value.name or ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    return str(value)[:300]


def form_changes(form):
    """[{campo, anterior, nuevo}] de los campos que cambió el formulario."""
    cambios = []
    for name in getattr(form, "changed_data", []):
        if any(fragment in name.lower() for fragment in SENSITIVE):
            continue
        field = form.fields.get(name)
        label = str(getattr(field, "label", "") or name)
        try:
            antes = form[name].initial
        except KeyError:
            antes = form.initial.get(name)
        if antes is not None and field is not None and hasattr(field, "queryset") and not hasattr(antes, "pk"):
            try:
                if isinstance(antes, (list, tuple)):
                    antes = list(field.queryset.filter(pk__in=antes))
                else:
                    antes = field.queryset.filter(pk=antes).first() or antes
            except Exception:
                pass
        cambios.append({"campo": label, "anterior": _plain(antes), "nuevo": _plain(form.cleaned_data.get(name))})
    return cambios


def _client_ip(request):
    """IP del cliente: X-Forwarded-For (proxy) o REMOTE_ADDR."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def audit(request, action, module='', object_repr='', detail='', changes=None):
    """Registra un evento de auditoría asociado al usuario de la request.

    Siempre continúa: un fallo de auditoría no debe romper el flujo.
    """
    user = getattr(request, 'user', None)
    if user is not None and not user.is_authenticated:
        user = None
    try:
        return AuditLog.objects.create(
            user=user,
            action=action,
            module=module or '',
            object_repr=(object_repr or '')[:200],
            detail=detail or '',
            ip=_client_ip(request),
            changes=json.dumps(changes, ensure_ascii=False) if changes else '',
        )
    except Exception:
        return None
