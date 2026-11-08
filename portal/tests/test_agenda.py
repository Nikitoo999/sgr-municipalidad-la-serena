import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from operaciones.models import Activity, Evidence, Task
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from sgr_core.models import InstitutionalGoal, Period

MEDIA_TMP = tempfile.mkdtemp(prefix="sgr_media_agenda_")


def pdf_file(name="respaldo.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n" + b"0" * 1024, content_type="application/pdf")


@override_settings(STORAGES=TEST_STORAGES, MEDIA_ROOT=MEDIA_TMP)
class AgendaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, MEDIA_TMP, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1565C0")
        periodo = Period.objects.create(
            name="Trimestre Oct-Dic 2026",
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), quarter=4,
        )
        g1 = InstitutionalGoal.objects.create(name="Meta Centro", weight=100, period=periodo, delegation=cls.d1)
        g2 = InstitutionalGoal.objects.create(name="Meta Av. del Mar", weight=100, period=periodo, delegation=cls.d2)

        User.objects.create_user(username="superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        User.objects.create_user(username="superadmin2", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, cls.roles["ROL04"],
                                first_name="Ana", last_name="Pérez")
        cls.luis = make_employee("luis", "10.000.002-2", cls.d2, cls.roles["ROL04"],
                                first_name="Luis", last_name="Rojas")
        cls.coord = make_employee("coord", "10.000.003-3", cls.d1, cls.roles["ROL02"])
        cls.coord.authorized_delegations.set([cls.d1])

        cls.t1 = Task.objects.create(goal=g1, title="Operativo Centro", due_date=date(2026, 12, 1), assigned_to=cls.ana)
        cls.t2 = Task.objects.create(goal=g2, title="Operativo Mar", due_date=date(2026, 12, 1), assigned_to=cls.luis)
        cls.act = Activity.objects.create(task=cls.t1, name="Reunión", execution_date=date(2026, 11, 5))

    def login(self, username="superadmin"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    # --- lista ---------------------------------------------------------
    def test_lista_muestra_codigo_de_tarea_y_actividades(self):
        self.login()
        resp = self.client.get(reverse("tasks"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.t1.code)
        self.assertContains(resp, "Reunión")

    # --- registrar actividad ------------------------------------------
    def test_registrar_actividad(self):
        self.login()
        resp = self.client.post(
            reverse("activity_create", args=[self.t1.pk]),
            {"name": "Visita a terreno", "execution_date": "2026-11-10"},
        )
        self.assertEqual(resp.status_code, 302)
        nueva = Activity.objects.get(name="Visita a terreno")
        self.assertEqual(nueva.task, self.t1)
        self.assertEqual(nueva.status, Activity.Status.PENDING)

    def test_registrar_actividad_sin_permiso_es_403(self):
        self.login("ana")
        resp = self.client.post(
            reverse("activity_create", args=[self.t1.pk]),
            {"name": "No debería", "execution_date": "2026-11-10"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Activity.objects.filter(name="No debería").exists())

    # --- evidencia -----------------------------------------------------
    def test_subir_evidencia_guarda_con_codigo_de_tarea(self):
        self.login()
        self.client.post(reverse("evidence_create", args=[self.act.pk]), {"file": pdf_file()})
        evidencia = Evidence.objects.get(activity=self.act)
        self.assertTrue(evidencia.file.name.startswith(f"evidencias/{self.t1.code}/"))
        self.act.refresh_from_db()
        self.assertEqual(self.act.status, Activity.Status.DONE)

    def test_subir_evidencia_rechaza_extension_no_permitida(self):
        self.login()
        archivo = SimpleUploadedFile("notas.txt", b"hola", content_type="text/plain")
        self.client.post(reverse("evidence_create", args=[self.act.pk]), {"file": archivo})
        self.assertFalse(Evidence.objects.filter(activity=self.act).exists())
        self.act.refresh_from_db()
        self.assertEqual(self.act.status, Activity.Status.PENDING)

    def test_no_se_puede_subir_evidencia_a_otra_delegacion(self):
        otra = Activity.objects.create(task=self.t2, name="Ajena", execution_date=date(2026, 11, 6))
        self.login("coord")
        resp = self.client.post(reverse("evidence_create", args=[otra.pk]), {"file": pdf_file()})
        # El coordinador no tiene permiso de crear: se rechaza antes de buscar la actividad.
        self.assertIn(resp.status_code, (403, 404))
        self.assertFalse(Evidence.objects.filter(activity=otra).exists())

    # --- validación ----------------------------------------------------
    def test_validar_evidencia_registra_quien_y_cuando(self):
        evidencia = Evidence.objects.create(activity=self.act)
        self.login()
        resp = self.client.post(reverse("evidence_validate", args=[evidencia.pk]))
        self.assertEqual(resp.status_code, 302)
        evidencia.refresh_from_db()
        self.assertTrue(evidencia.is_validated)
        self.assertEqual(evidencia.validated_by.username, "superadmin")
        self.assertIsNotNone(evidencia.validated_at)

    def test_validar_dos_veces_no_cambia_quien_valido(self):
        evidencia = Evidence.objects.create(activity=self.act)
        self.login("superadmin")
        self.client.post(reverse("evidence_validate", args=[evidencia.pk]))
        self.client.logout()
        self.login("superadmin2")
        self.client.post(reverse("evidence_validate", args=[evidencia.pk]))
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.validated_by.username, "superadmin")

    def test_validar_sin_permiso_es_403(self):
        evidencia = Evidence.objects.create(activity=self.act)
        self.login("coord")
        resp = self.client.post(reverse("evidence_validate", args=[evidencia.pk]))
        self.assertEqual(resp.status_code, 403)
        evidencia.refresh_from_db()
        self.assertFalse(evidencia.is_validated)