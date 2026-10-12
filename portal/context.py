from .access import active_delegation, allowed_delegations, get_role, user_permissions


def sgr_context(request):
    """Datos de cabecera: delegación activa, rol y permisos (solo para mostrar; el control real es en servidor)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    role = get_role(user)
    return {
        "sgr_active_delegation": active_delegation(request),
        "sgr_allowed_delegations": list(allowed_delegations(user, only_active=True)),
        "sgr_role_name": role.name if role else ("Superusuario" if user.is_superuser else ""),
        "sgr_perms": user_permissions(user),
    }
