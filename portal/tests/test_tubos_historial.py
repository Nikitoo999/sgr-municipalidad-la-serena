"""Tubo como agenda colectiva (RF-016 a RF-021): historial, plazos y resumen."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones.models import RecordComment, TubeEntry, TubeStatusChange
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee, make_user,
)
from portal.tubes_views import marcar_plazos, resumen_por_funcionario


@override_settings(STORAGES=TEST_STORAGES)
class TuboHistorialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        make_user("superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, roles["ROL04"], first_name="Ana", last_name="Pérez")
        cls.luis = make_employee("luis", "10.000.002-2", cls.d1, roles["ROL04"], first_name="Luis", last_name="Rojas")
        hoy = timezone.localdate()
        cls.t1 = TubeEntry.objects.create(
            delegation=cls.d1, title="Poda en plaza", requester="JJVV Centro", contact_phone="+56911111111",
            responsible=cls.ana, request_date=hoy, due_date=hoy + timedelta(days=2),
        )

    def setUp(self):
        self.client.login(username="superadmin", password=DEMO_PASSWORD)

    def test_cambio_de_estado_queda_en_historial_con_observacion(self):
        self.client.post(reverse("tube_status", args=[self.t1.pk]),
                         {"status": "in_progress", "notes": "Cuadrilla asignada"})
        cambio = TubeStatusChange.objects.get(entry=self.t1, kind="status")
        self.assertEqual((cambio.from_value, cambio.to_value), ("Ingresado", "En proceso"))
        self.assertEqual(cambio.notes, "Cuadrilla asignada")
        self.assertEqual(cambio.changed_by.username, "superadmin")

    def test_ingreso_registra_historial(self):
        self.client.post(reverse("tube_create"), {
            "delegation": self.d1.pk, "channel": "delegation", "title": "Bache en pasaje",
            "origin": "EXT", "requester": "Vecino", "request_date": timezone.localdate().isoformat(),
        })
        nueva = TubeEntry.objects.get(title="Bache en pasaje")
        self.assertTrue(nueva.history.filter(kind="created").exists())

    def test_reprogramar_exige_motivo(self):
        url = reverse("tube_reschedule", args=[self.t1.pk])
        nueva = (timezone.localdate() + timedelta(days=10)).isoformat()
        self.client.post(url, {"due_date": nueva, "notes": ""})
        self.t1.refresh_from_db()
        self.assertNotEqual(self.t1.due_date.isoformat(), nueva)
        self.client.post(url, {"due_date": nueva, "notes": "Falta material, se avisó al vecino"})
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.due_date.isoformat(), nueva)
        self.assertTrue(self.t1.history.filter(kind="reschedule").exists())

    def test_reasignar_responsable(self):
        self.client.post(reverse("tube_reassign", args=[self.t1.pk]),
                         {"responsible": self.luis.pk, "notes": "Ana con vacaciones"})
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.responsible, self.luis)
        cambio = self.t1.history.get(kind="reassign")
        self.assertEqual((cambio.from_value, cambio.to_value), ("Ana Pérez", "Luis Rojas"))

    def test_detalle_en_ventana_y_comentario(self):
        resp = self.client.get(reverse("tube_detail", args=[self.t1.pk]), {"modal": "1"})
        self.assertEqual(resp["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(resp, "Reprogramar compromiso")
        resp = self.client.post(reverse("tube_comment", args=[self.t1.pk]) + "?modal=1",
                                {"text": "Coordinar con Aseo y Ornato"})
        # En la ventana emergente, al guardar se avisa a la página para cerrar y recargar.
        self.assertContains(resp, "sgr-modal-redirect")
        self.assertTrue(RecordComment.objects.filter(tube_entry=self.t1).exists())

    def test_plazos_y_resumen(self):
        hoy = timezone.localdate()
        marcar_plazos(self.t1, hoy)
        self.assertTrue(self.t1.proxima)
        self.assertFalse(self.t1.vencida)
        TubeEntry.objects.create(
            delegation=self.d1, title="Atrasada", requester="X", responsible=self.ana,
            request_date=hoy - timedelta(days=20), due_date=hoy - timedelta(days=5),
        )
        filas, total = resumen_por_funcionario(TubeEntry.objects.all(), hoy)
        self.assertEqual(filas[0]["nombre"], "Ana Pérez")
        self.assertEqual((filas[0]["total"], filas[0]["vencidas"]), (2, 1))
        self.assertEqual(total["pct"], 0.0)
        self.assertFalse(total["cumple"])
