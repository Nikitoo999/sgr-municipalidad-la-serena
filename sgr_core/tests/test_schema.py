"""Pruebas del esquema de la Parte 2B (sgr_core)."""

from django.core.management import call_command
from django.db import connection, transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.test import TestCase, override_settings

from portal.tests.utils import TEST_STORAGES
from sgr_core.models import AttentionSubtype, AttentionType, ProjectItem


@override_settings(STORAGES=TEST_STORAGES)
class CatalogSchemaTests(TestCase):
    def test_tablas_con_nombre_de_convencion(self):
        tables = connection.introspection.table_names()
        for expected in ("item_proyecto", "tipo_atencion", "sub_atencion"):
            self.assertIn(expected, tables)

    def test_codigos_unicos(self):
        from django.db import IntegrityError
        ProjectItem.objects.create(code="ITM01", name="Uno")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProjectItem.objects.create(code="ITM01", name="Duplicado")
        AttentionType.objects.create(code="TAT01", name="Uno")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttentionType.objects.create(code="TAT01", name="Duplicado")

    def test_protected_al_borrar_tipo_con_subtipos(self):
        tipo = AttentionType.objects.create(code="TAT01", name="Social")
        AttentionSubtype.objects.create(code="SAT01", name="Ayuda", attention_type=tipo)
        # RESTRICT se manifiesta como RestrictedError (hermana de ProtectedError).
        with self.assertRaises((ProtectedError, RestrictedError)):
            tipo.delete()

    def test_alive_excluye_borrado_logico(self):
        from django.utils import timezone
        ProjectItem.objects.create(code="ITM01", name="Vivo")
        borrado = ProjectItem.objects.create(code="ITM02", name="Borrado")
        borrado.deleted_at = timezone.now()
        borrado.save(update_fields=["deleted_at"])
        self.assertEqual(ProjectItem.objects.count(), 2)
        self.assertEqual(
            set(ProjectItem.alive.values_list("code", flat=True)), {"ITM01"}
        )

    def test_seed_idempotente(self):
        call_command("seed_demo", verbosity=0)
        conteos = (
            ProjectItem.objects.count(),
            AttentionType.objects.count(),
            AttentionSubtype.objects.count(),
        )
        self.assertEqual(conteos, (7, 5, 8))
        call_command("seed_demo", verbosity=0)
        self.assertEqual(
            (
                ProjectItem.objects.count(),
                AttentionType.objects.count(),
                AttentionSubtype.objects.count(),
            ),
            conteos,
        )

    def test_docs_mencionan_tablas(self):
        from pathlib import Path
        from django.conf import settings
        doc = Path(settings.BASE_DIR) / "docs" / "db" / "modelo_entidad_relacion.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        for table in ("item_proyecto", "tipo_atencion", "sub_atencion", "atencion", "vecino"):
            self.assertIn(table, text)

    def test_sin_cambios_pendientes(self):
        call_command("makemigrations", check=True, dry_run=True, verbosity=0)


class DocsCommandTests(TestCase):
    def test_comando_regenera_docs(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "modelo_entidad_relacion.md"
            call_command("generar_modelo_docs", output=str(out), verbosity=0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("erDiagram", text)
            self.assertIn("atencion", text)
