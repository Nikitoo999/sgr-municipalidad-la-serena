"""Flujo completo de la matriz (Unidad 3): de la atención al puntaje.

- Funcionario como civil (detección por RUT, nunca bloquea) y regla 1 del
  nuevo requerimiento (gestión interna no suma) y regla 6 (ingreso propio).
- Comparecencia "Directivo de organización" con organigrama.
- Ítem de la matriz limitado a los ítems del cargo del responsable.
- Validación del punto (RN-009): aprobar exige evidencia; rechazar exige
  observación; nadie valida lo que registró; una atención aprobada suma.
- Revisión de evidencias de la agenda (RF-013) y punto 2 (contacto).
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones.calculos import logrado_por_item
from operaciones.models import Activity, Attention, Evidence, Neighbor, Task
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee,
)
from portal.validators import format_rut, rut_check_digit
from sgr_core.models import (
    AttentionSubtype, AttentionType, CommunityOrganization, DirectiveRole, InstitutionalGoal,
    OrganizationMember, Period, Position, PositionItemGoal, ProjectItem,
)


def rut(body):
    """RUT válido (con dígito verificador correcto) para un cuerpo numérico."""
    return format_rut(str(body), rut_check_digit(str(body)))


class MatrizBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")
        hoy = timezone.localdate()
        cls.periodo = Period.objects.create(
            name="Trimestre de prueba", start_date=hoy - timedelta(days=40),
            end_date=hoy + timedelta(days=40), quarter=4,
        )
        cls.cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        cls.item = ProjectItem.objects.create(code="MTX01", name="Atención social a usuario presencial")
        cls.item_otro = ProjectItem.objects.create(code="MTX09", name="Informe de inventarios",
                                                   requires_contact=False)
        PositionItemGoal.objects.create(position=cls.cargo, item=cls.item, period=cls.periodo,
                                        weight=100, target_value=10)
        cls.delegado = make_employee("delegado", rut(15000001), cls.d1, cls.roles["ROL03"],
                                     first_name="Delia", last_name="Delegada")
        cls.ana = make_employee("ana", rut(15000002), cls.d1, cls.roles["ROL04"],
                                first_name="Ana", last_name="Pérez")
        cls.ana.position = cls.cargo
        cls.ana.save()
        cls.luis = make_employee("luis", rut(15000003), cls.d1, cls.roles["ROL04"],
                                 first_name="Luis", last_name="Rojas")
        cls.tipo = AttentionType.objects.create(code="TAT01", name="Social")
        cls.sub = AttentionSubtype.objects.create(code="SAT01", name="Informe aporte material",
                                                  attention_type=cls.tipo, item=cls.item)

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=DEMO_PASSWORD))

    def datos(self, **extra):
        data = {
            "requester_mode": "person",
            "neighbor_rut": rut(16000001), "neighbor_name": "María González",
            "neighbor_phone": "+56 9 1111 1111",
            "attention_type": str(self.tipo.pk), "attention_subtype": str(self.sub.pk),
            "item": str(self.item.pk),
            "description": "Solicita retiro de aporte material para su vivienda.",
        }
        data.update(extra)
        return data


@override_settings(STORAGES=TEST_STORAGES)
class FuncionarioComoCivilTests(MatrizBase):
    def test_rut_de_funcionario_pide_elegir_sin_bloquear(self):
        self.login("ana")
        resp = self.client.post(reverse("attentions_new"), self.datos(
            neighbor_rut=self.luis.rut, neighbor_name="Luis Rojas"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "corresponde a un funcionario municipal")
        self.assertFalse(Attention.objects.exists())

    def test_funcionario_como_civil_queda_vinculado_y_suma(self):
        self.login("ana")
        resp = self.client.post(reverse("attentions_new"), self.datos(
            neighbor_rut=self.luis.rut, neighbor_name="Luis Rojas", employee_relation="civil"))
        self.assertEqual(resp.status_code, 302)
        atencion = Attention.objects.get()
        self.assertEqual(atencion.requester_employee, self.luis)
        self.assertEqual(atencion.employee_relation, "civil")
        self.assertTrue(atencion.counts_for_score)
        # Misma persona: el vecino queda vinculado al funcionario (sin duplicar).
        self.assertEqual(Neighbor.objects.get(identifier=self.luis.rut).employee, self.luis)

    def test_gestion_interna_no_suma(self):
        self.login("ana")
        self.client.post(reverse("attentions_new"), self.datos(
            neighbor_rut=self.delegado.rut, neighbor_name="Delia Delegada", employee_relation="internal"))
        atencion = Attention.objects.get()
        self.assertFalse(atencion.counts_for_score)
        self.assertIn("gestión interna", atencion.score_display)

    def test_ingreso_propio_no_suma(self):
        self.login("ana")
        self.client.post(reverse("attentions_new"), self.datos(
            neighbor_rut=self.ana.rut, neighbor_name="Ana Pérez", employee_relation="civil"))
        atencion = Attention.objects.get()
        self.assertFalse(atencion.counts_for_score)
        self.assertIn("propia solicitud", atencion.score_display)

    def test_consulta_por_rut(self):
        self.login("ana")
        resp = self.client.get(reverse("attention_rut_check"), {"rut": self.luis.rut})
        self.assertEqual(resp.json()["employee"]["name"], "Luis Rojas")
        # Un fragmento no permite enumerar funcionarios.
        resp = self.client.get(reverse("attention_rut_check"), {"rut": "15000"})
        self.assertIsNone(resp.json()["employee"])


@override_settings(STORAGES=TEST_STORAGES)
class DirectivoTests(MatrizBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.presidente = DirectiveRole.objects.get(name="Presidente/a")
        cls.org = CommunityOrganization.objects.create(name="JJVV VILLA EL FARO", delegation=cls.d1)
        cls.org_otra = CommunityOrganization.objects.create(name="CLUB LOS AROMOS", delegation=cls.d1)
        cls.integrante = OrganizationMember.objects.create(
            organization=cls.org, role=cls.presidente, full_name="Patricia Soto",
            rut=rut(17000001), phone="+56984123310",
        )

    def test_directivo_exige_organizacion(self):
        self.login("ana")
        resp = self.client.post(reverse("attentions_new"), self.datos(requester_mode="directive"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Attention.objects.exists())

    def test_directivo_del_organigrama(self):
        self.login("ana")
        resp = self.client.post(reverse("attentions_new"), self.datos(
            requester_mode="directive", organization=str(self.org.pk),
            organization_member=str(self.integrante.pk),
            neighbor_rut=self.integrante.rut, neighbor_name="Patricia Soto"))
        self.assertEqual(resp.status_code, 302)
        atencion = Attention.objects.get()
        self.assertEqual(atencion.organization, self.org)
        self.assertEqual(atencion.directive_role, self.presidente)  # tomado del integrante
        self.assertIn("Presidente/a", atencion.requester_display)

    def test_integrante_de_otra_organizacion_se_rechaza(self):
        self.login("ana")
        self.client.post(reverse("attentions_new"), self.datos(
            requester_mode="directive", organization=str(self.org_otra.pk),
            organization_member=str(self.integrante.pk), directive_role=str(self.presidente.pk)))
        self.assertFalse(Attention.objects.exists())

    def test_busqueda_y_directiva_json(self):
        self.login("ana")
        resp = self.client.get(reverse("organization_lookup"), {"q": "faro"})
        self.assertEqual([r["label"] for r in resp.json()["results"]], ["JJVV VILLA EL FARO"])
        resp = self.client.get(reverse("organization_members_json", args=[self.org.pk]))
        self.assertEqual(resp.json()["members"][0]["name"], "Patricia Soto")


@override_settings(STORAGES=TEST_STORAGES)
class ItemYValidacionTests(MatrizBase):
    def crear(self, username="ana"):
        self.login(username)
        self.client.post(reverse("attentions_new"), self.datos())
        return Attention.objects.latest("pk")

    def test_item_fuera_del_cargo_se_rechaza(self):
        self.login("ana")
        resp = self.client.post(reverse("attentions_new"), self.datos(item=str(self.item_otro.pk)))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Attention.objects.exists())

    def test_aprobar_exige_evidencia_y_rechazar_exige_observacion(self):
        atencion = self.crear()
        self.login("delegado")
        url = reverse("attention_review", args=[atencion.pk])
        self.client.post(url, {"decision": "approved"})
        atencion.refresh_from_db()
        self.assertEqual(atencion.validation_status, "pending")
        self.client.post(url, {"decision": "rejected", "notes": ""})
        atencion.refresh_from_db()
        self.assertEqual(atencion.validation_status, "pending")
        self.client.post(url, {"decision": "rejected", "notes": "Falta la foto del retiro."})
        atencion.refresh_from_db()
        self.assertEqual(atencion.validation_status, "rejected")
        self.assertEqual(atencion.validated_by, self.delegado.user)

    def test_funcionario_no_valida(self):
        atencion = self.crear()
        self.login("luis")
        resp = self.client.post(reverse("attention_review", args=[atencion.pk]), {"decision": "approved"})
        self.assertEqual(resp.status_code, 403)

    def test_atencion_aprobada_suma_a_la_matriz(self):
        atencion = self.crear()
        Attention.objects.filter(pk=atencion.pk).update(attachment="atenciones/documentos/respaldo.pdf")
        self.assertEqual(logrado_por_item(self.ana, self.periodo), {})
        self.login("delegado")
        self.client.post(reverse("attention_review", args=[atencion.pk]), {"decision": "approved"})
        atencion.refresh_from_db()
        self.assertEqual(atencion.validation_status, "approved")
        self.assertEqual(logrado_por_item(self.ana, self.periodo), {self.item.pk: 1})

    def test_editar_dato_que_puntua_reinicia_la_validacion(self):
        atencion = self.crear()
        Attention.objects.filter(pk=atencion.pk).update(validation_status="approved")
        self.login("delegado")
        self.client.post(reverse("attentions_edit", args=[atencion.pk]), {
            "attention_type": str(self.tipo.pk), "attention_subtype": str(self.sub.pk), "item": "",
            "description": atencion.description, "status": "received",
        })
        atencion.refresh_from_db()
        self.assertIsNone(atencion.item_id)
        self.assertEqual(atencion.validation_status, "pending")

    def test_comentario_en_la_atencion(self):
        atencion = self.crear()
        self.client.post(reverse("attention_comment", args=[atencion.pk]), {"text": "Llamar el lunes."})
        detalle = self.client.get(reverse("attentions_detail", args=[atencion.pk]))
        self.assertContains(detalle, "Llamar el lunes.")


@override_settings(STORAGES=TEST_STORAGES)
class EvidenciaYContactoTests(MatrizBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        meta = InstitutionalGoal.objects.create(name="Meta", period=cls.periodo, delegation=cls.d1)
        cls.tarea = Task.objects.create(goal=meta, title="Operativo", due_date=date(2026, 12, 1),
                                        assigned_to=cls.ana)

    def actividad(self, item, contacto=("", "")):
        act = Activity.objects.create(
            task=self.tarea, name="Act", execution_date=timezone.localdate(),
            status=Activity.Status.DONE, item=item,
            contact_name=contacto[0], contact_phone=contacto[1],
        )
        return act, Evidence.objects.create(activity=act)

    def test_rechazar_evidencia_con_observacion(self):
        _act, evidencia = self.actividad(self.item)
        self.login("delegado")
        url = reverse("evidence_validate", args=[evidencia.pk])
        self.client.post(url, {"decision": "correction", "notes": ""})
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.review_status, "pending")
        self.client.post(url, {"decision": "rejected", "notes": "La foto no corresponde."})
        evidencia.refresh_from_db()
        self.assertEqual(evidencia.review_status, "rejected")
        self.assertFalse(evidencia.is_validated)

    def test_sin_contacto_no_suma_si_el_item_lo_exige(self):
        _a, ev1 = self.actividad(self.item)
        _b, ev2 = self.actividad(self.item_otro)
        Evidence.objects.filter(pk__in=[ev1.pk, ev2.pk]).update(is_validated=True, review_status="approved")
        # El ítem interno (no exige contacto) no está en las metas del cargo, pero
        # el cálculo lo reporta; el de cara al usuario sin contacto no suma.
        self.assertEqual(logrado_por_item(self.ana, self.periodo), {self.item_otro.pk: 1})
        _c, ev3 = self.actividad(self.item, contacto=("Vecina", "+56 9 1234 5678"))
        Evidence.objects.filter(pk=ev3.pk).update(is_validated=True, review_status="approved")
        self.assertEqual(logrado_por_item(self.ana, self.periodo), {self.item_otro.pk: 1, self.item.pk: 1})

    def test_actividad_de_semana_cerrada_se_rechaza(self):
        self.login("ana")
        vieja = timezone.localdate() - timedelta(days=21)
        self.client.post(reverse("activity_create", args=[self.tarea.pk]),
                         {"name": "Atrasada", "execution_date": vieja.isoformat()})
        self.assertFalse(Activity.objects.filter(name="Atrasada").exists())


@override_settings(STORAGES=TEST_STORAGES)
class PanelRitmoTests(MatrizBase):
    def test_inicio_muestra_ritmo_personal(self):
        self.login("ana")
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Ritmo del período · Trimestre de prueba")
        self.assertEqual(resp.context["ritmo"]["alcance"], "personal")
        self.assertContains(resp, "Ritmo sugerido para cerrar al 100 %")

    def test_delegado_ve_ritmo_del_equipo_y_graficos(self):
        self.login("delegado")
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.context["ritmo"]["alcance"], "equipo")
        graficos = self.client.get(reverse("reports_charts"))
        self.assertEqual(graficos.status_code, 200)
        self.assertContains(graficos, "Ritmo acumulado: avance real vs. esperado")
        self.assertContains(graficos, "<polyline", html=False)


@override_settings(STORAGES=TEST_STORAGES)
class ReasignacionYFotoTests(MatrizBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        meta = InstitutionalGoal.objects.create(name="Meta", period=cls.periodo, delegation=cls.d1)
        cls.tarea = Task.objects.create(goal=meta, title="Operativo", due_date=date(2026, 12, 1), assigned_to=cls.ana)

    def test_delegado_reasigna_tarea_con_motivo(self):
        from operaciones.models import TaskReassignment

        self.login("delegado")
        self.client.post(reverse("task_reassign", args=[self.tarea.pk]),
                         {"employee": self.luis.pk, "reason": "vacation", "notes": "Ana de vacaciones"})
        self.tarea.refresh_from_db()
        self.assertEqual(self.tarea.assigned_to, self.luis)
        registro = TaskReassignment.objects.get(task=self.tarea)
        self.assertEqual((registro.original_employee, registro.reassigned_employee, registro.reason),
                         (self.ana, self.luis, "vacation"))

    def test_funcionario_no_reasigna(self):
        self.login("luis")
        resp = self.client.post(reverse("task_reassign", args=[self.tarea.pk]),
                                {"employee": self.luis.pk, "reason": "other"})
        self.assertEqual(resp.status_code, 403)

    def test_foto_de_perfil(self):
        import io
        import shutil
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        media = tempfile.mkdtemp(prefix="sgr_foto_")
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        buffer = io.BytesIO()
        Image.new("RGB", (40, 40), "red").save(buffer, format="PNG")
        with self.settings(MEDIA_ROOT=media):
            self.login("ana")
            self.client.post(reverse("profile"), {
                "action": "update_photo", "photo": SimpleUploadedFile("yo.png", buffer.getvalue(), "image/png"),
            })
            self.ana.refresh_from_db()
            self.assertTrue(self.ana.photo.name.startswith("perfiles/"))
            inicio = self.client.get(reverse("home"))
            self.assertContains(inicio, "avatar-img")
            self.client.post(reverse("profile"), {"action": "update_photo",
                                                  "photo": SimpleUploadedFile("x.png", b"no es imagen", "image/png")})
            self.ana.refresh_from_db()
            self.assertTrue(self.ana.photo)  # la foto válida anterior se conserva
            self.client.post(reverse("profile"), {"action": "remove_photo"})
            self.ana.refresh_from_db()
            self.assertFalse(self.ana.photo)
