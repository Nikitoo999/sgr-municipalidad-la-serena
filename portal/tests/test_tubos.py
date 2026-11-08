"""Pruebas de la pantalla de tubos: alcance, estados y cierre con código de verificación (3.6)."""
import io
import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from operaciones.models import TubeEntry
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)

MEDIA_TMP = tempfile.mkdtemp(prefix="sgr_media_tubos_")


def png_file(name="foto.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(STORAGES=TEST_STORAGES, MEDIA_ROOT=MEDIA_TMP)
class TubosTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, MEDIA_TMP, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1565C0")
        User.objects.create_user(username="superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, roles["ROL04"], first_name="Ana", last_name="Pérez")
        cls.luis = make_employee("luis", "10.000.002-2", cls.d2, roles["ROL04"], first_name="Luis", last_name="Rojas")
        cls.coord = make_employee("coord", "10.000.003-3", cls.d1, roles["ROL02"])
        cls.coord.authorized_delegations.set([cls.d1])

        cls.t1 = TubeEntry.objects.create(
            delegation=cls.d1, title="Poda en Las Compañías", requester="JJVV Centro",
            responsible=cls.ana, request_date=date(2026, 11, 2),
        )
        cls.t2 = TubeEntry.objects.create(
            delegation=cls.d2, title="Reparación en Avenida del Mar", requester="Club Deportivo",
            responsible=cls.luis, request_date=date(2026, 11, 3),
        )

    def login(self, username="superadmin"):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def datos_nueva(self, **extra):
        datos = {
            "delegation": self.d1.pk, "channel": "delegation", "title": "Limpieza de sitio eriazo",
            "origin": "EXT", "requester": "Vecina", "request_date": "2026-11-05",
            "responsible": self.ana.pk,
        }
        datos.update(extra)
        return datos

    # --- lista y alcance ------------------------------------------------
    def test_tubo_general_muestra_todas_las_delegaciones(self):
        self.login()
        resp = self.client.get(reverse("tubes"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Poda en Las Compañías")
        self.assertContains(resp, "Reparación en Avenida del Mar")

    def test_coordinador_solo_ve_su_delegacion(self):
        self.login("coord")
        resp = self.client.get(reverse("tubes"))
        self.assertContains(resp, "Poda en Las Compañías")
        self.assertNotContains(resp, "Reparación en Avenida del Mar")

    def test_funcionario_puede_ver_pero_no_crear_tubos(self):
        self.login("ana")
        self.assertEqual(self.client.get(reverse("tubes")).status_code, 200)
        resp = self.client.post(reverse("tube_create"), {"title": "No debería"})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(TubeEntry.objects.filter(title="No debería").exists())

    def test_filtro_por_canal(self):
        TubeEntry.objects.create(
            delegation=self.d1, channel="letters", title="Carta de prueba", requester="X",
            request_date=date(2026, 11, 4),
        )
        self.login()
        resp = self.client.get(reverse("tubes"), {"canal": "letters"})
        self.assertContains(resp, "Carta de prueba")
        self.assertNotContains(resp, "Poda en Las Compañías")

    # --- ingreso ---------------------------------------------------------
    def test_ingresar_solicitud_genera_codigo_de_verificacion(self):
        self.login()
        self.client.post(reverse("tube_create"), self.datos_nueva())
        nueva = TubeEntry.objects.get(title="Limpieza de sitio eriazo")
        self.assertEqual(len(nueva.verification_code), 6)
        self.assertEqual(nueva.status, TubeEntry.Status.RECEIVED)

    def test_responsable_de_otra_delegacion_se_rechaza(self):
        self.login()
        self.client.post(reverse("tube_create"), self.datos_nueva(responsible=self.luis.pk))
        self.assertFalse(TubeEntry.objects.filter(title="Limpieza de sitio eriazo").exists())

    # --- estados ---------------------------------------------------------
    def test_cambiar_estatus(self):
        self.login()
        self.client.post(reverse("tube_status", args=[self.t1.pk]), {"status": "in_progress"})
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, TubeEntry.Status.IN_PROGRESS)

    def test_realizado_no_se_puede_poner_a_mano(self):
        self.login()
        self.client.post(reverse("tube_status", args=[self.t1.pk]), {"status": "done"})
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, TubeEntry.Status.RECEIVED)

    # --- cierre con foto y código ---------------------------------------
    def test_cerrar_con_codigo_y_foto(self):
        self.login()
        self.client.post(
            reverse("tube_close", args=[self.t1.pk]),
            {"proof_image": png_file(), "code": self.t1.verification_code.lower()},
        )
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, TubeEntry.Status.DONE)
        self.assertIsNotNone(self.t1.completed_at)
        self.assertTrue(self.t1.proof_image.name.startswith("tubos/"))

    def test_codigo_incorrecto_no_cierra(self):
        self.login()
        self.client.post(
            reverse("tube_close", args=[self.t1.pk]), {"proof_image": png_file(), "code": "ZZZZZZ"},
        )
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, TubeEntry.Status.RECEIVED)

    def test_cerrar_sin_foto_no_cierra(self):
        self.login()
        self.client.post(reverse("tube_close", args=[self.t1.pk]), {"code": self.t1.verification_code})
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.status, TubeEntry.Status.RECEIVED)

    def test_funcionario_no_puede_cerrar(self):
        self.login("ana")
        resp = self.client.post(
            reverse("tube_close", args=[self.t1.pk]),
            {"proof_image": png_file(), "code": self.t1.verification_code},
        )
        self.assertEqual(resp.status_code, 403)