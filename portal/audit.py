"""Auditoría mínima de accesos y acciones relevantes."""
from .models import AuditLog


def _client_ip(request):
    """IP del cliente: X-Forwarded-For (proxy) o REMOTE_ADDR."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def audit(request, action, module='', object_repr='', detail=''):
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
        )
    except Exception:
        return None
