from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Permite ingresar con nombre de usuario o correo (sin distinguir mayúsculas)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        username = username or kwargs.get(User.USERNAME_FIELD)
        if not username or not password:
            return None
        candidates = list(User.objects.filter(Q(username__iexact=username.strip()) | Q(email__iexact=username.strip()))[:2])
        if len(candidates) != 1:  # inexistente o ambiguo
            User().set_password(password)  # iguala tiempos de respuesta
            return None
        user = candidates[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
