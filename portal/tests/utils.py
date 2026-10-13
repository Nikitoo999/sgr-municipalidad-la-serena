"""Utilidades compartidas por las pruebas de las distintas apps.

`TEST_STORAGES` reemplaza el backend de estáticos durante los tests: los tests no
ejecutan `collectstatic` y `CompressedManifestStaticFilesStorage` (configurado en
producción) lanza "Missing staticfiles manifest entry" al renderizar `{% static %}`.
"""

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
