from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class EmailOrUsernameBackend(ModelBackend):
    """Acepta nombre de usuario o correo electrónico, sin distinguir mayúsculas."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username:
            return None
        # Si contiene @ puede ser un correo electrónico
        if '@' in str(username):
            try:
                user = User.objects.get(email__iexact=username)
            except User.DoesNotExist:
                return None
        else:
            try:
                user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                return None
        if user.check_password(password):
            return user
        return None
