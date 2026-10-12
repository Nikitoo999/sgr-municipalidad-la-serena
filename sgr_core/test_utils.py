"""Utilidades compartidas por las pruebas.

En las pruebas DEBUG=False y settings usa ManifestStaticFilesStorage (necesita
`collectstatic`). Para no depender de eso se usa el almacenamiento simple.
"""
from django.test import override_settings

PLAIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

plain_static = override_settings(STORAGES=PLAIN_STORAGES, ALLOWED_HOSTS=["testserver", "localhost"])
