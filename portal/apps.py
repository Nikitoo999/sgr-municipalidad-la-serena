from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'portal'

    def ready(self):
        # Búsqueda sin tildes en SQLite resuelta en la base de datos: registra
        # la función SQL ``sgr_normalizar`` en cada conexión nueva (en
        # MariaDB la collation utf8mb4 ya ignora tildes y mayúsculas).
        from django.db.backends.signals import connection_created

        from .crud.search import register_sqlite_functions

        connection_created.connect(
            register_sqlite_functions, dispatch_uid="sgr_sqlite_functions",
        )
