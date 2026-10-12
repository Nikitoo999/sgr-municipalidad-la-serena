from django.conf import settings
from django.db import models


class PasswordResetCode(models.Model):
    """Código de 6 dígitos para recuperar contraseña. Se guarda solo su hash (nunca el código)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reset_codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "codigo_recuperacion"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]
