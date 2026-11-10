"""Pruebas de la pantalla de cumplimiento y del registro de felicitaciones/reclamos (3.6)."""
import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from operaciones.models import EmployeeFeedback
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from sgr_core.models import Period, Position, PositionItemGoal, ProjectItem

MEDIA_TMP = tempfile.mkdtemp(prefix="sgr_media_cumpl_")


def pdf_file(name="respaldo.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n" + b"0" * 1024, content_type="application/pdf")


@override_settings(STORAGES=TEST_STORAGES, MEDIA_ROOT=MEDIA_TMP)
class FeedbackViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, MEDIA_TMP, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        roles = ensure_roles()
        delegacion = make_delegation("Centro", "DEL01", color="#C62828")
        periodo = Period.objects.create(
            name="Trimestre Oct-Dic 2026",
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), quarter=4,
        )
        cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        item = ProjectItem.objects.create(code="MTX01", name="Atención social")
        PositionItemGoal.objects.create(position=cargo, item=item, period=periodo, weight=100, target_value=10)
        User.objects.create_user(username="superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.ana = make_employee("ana", "10.000.001-1", delegacion, roles["ROL04"],
                                first_name="Ana", last_name="Pérez")
        cls.ana.position = cargo
        cls.ana.save()
        cls.url = reverse("feedback_create", args=[cls.ana.pk])

    def login(self, username="superadmin"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def test_registrar_reclamo(self):
        self.login()
        resp = self.client.post(self.url, {"kind": "complaint", "date": "2026-11-03", "description": "Demora"})
        self.assertEqual(resp.status_code, 302)
        registro = EmployeeFeedback.objects.get(employee=self.ana)
        self.assertEqual(registro.kind, "complaint")
        self.assertEqual(registro.registered_by.username, "superadmin")

    def test_felicitacion_sin_archivo_se_rechaza(self):
        self.login()
        self.client.post(self.url, {"kind": "praise", "date": "2026-11-03", "description": "Buen trato"})
        self.assertFalse(EmployeeFeedback.objects.filter(employee=self.ana).exists())

    def test_felicitacion_con_archivo_se_guarda(self):
        self.login()
        self.client.post(self.url, {
            "kind": "praise", "date": "2026-11-03", "description": "Buen trato", "file": pdf_file(),
        })
        registro = EmployeeFeedback.objects.get(employee=self.ana)
        self.assertTrue(registro.file.name.startswith("respaldos/"))

    def test_funcionario_no_puede_registrar(self):
        self.login("ana")
        resp = self.client.post(self.url, {"kind": "complaint", "date": "2026-11-03", "description": "x"})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(EmployeeFeedback.objects.exists())

    def test_la_pantalla_muestra_el_resumen(self):
        self.login()
        resp = self.client.get(reverse("achievements"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ana Pérez")
        self.assertContains(resp, "Felicitaciones y reclamos")