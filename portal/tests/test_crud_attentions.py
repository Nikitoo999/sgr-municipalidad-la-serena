"""Pruebas de la Parte 7: módulo de Atenciones.

Cubre: alcance por rol en listado/consulta/edición/exportación, el funcionario
no abre atenciones ajenas por URL (403), POST manipulado rechazado (delegación
no permitida, tipo inactivo, subtipo de otro tipo, solicitante inexistente,
descripción corta), número automático y único, endpoint JSON con sesión y
permiso, cambio de delegación activa, exportación con filtros y doble envío.
"""

import io

from django.test import TestCase, override_settings
from django.urls import reverse

from openpyxl import load_workbook

from operaciones.models import Attention, Neighbor
from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
    make_user,
)
from sgr_core.models import AttentionSubtype, AttentionType


@override_settings(STORAGES=TEST_STORAGES)
class AttentionsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")
        cls.d3 = make_delegation("La Antena-La Florida", "DEL03", color="#2E7D32")
        cls.d_inactiva = make_delegation("Cerrada", "DEL99", status="Inactiva")

        cls.superadmin = make_user(
            "superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        cls.coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coordinador.authorized_delegations.set([cls.d1, cls.d2])
        cls.delegado = make_employee(
            "delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"],
        )
        cls.funcionario = make_employee(
            "funcionario", "11.111.113-3", cls.d1, cls.roles["ROL04"],
        )
        cls.otro_funcionario = make_employee(
            "otro.funcionario", "11.111.114-4", cls.d2, cls.roles["ROL04"],
        )

        cls.tipo = AttentionType.objects.create(code="TAT01", name="Social")
        cls.tipo_inactivo = AttentionType.objects.create(
            code="TAT99", name="Emergencias", status="Inactivo",
        )
        cls.otro_tipo = AttentionType.objects.create(code="TAT02", name="Territorial")
        cls.sub = AttentionSubtype.objects.create(
            code="SAT01", name="Ayuda social", attention_type=cls.tipo,
        )
        cls.sub_otro_tipo = AttentionSubtype.objects.create(
            code="SAT03", name="Visita a terreno", attention_type=cls.otro_tipo,
        )
        cls.sub_inactivo = AttentionSubtype.objects.create(
            code="SAT99", name="Consulta general", attention_type=cls.tipo,
            status="Inactivo",
        )

        cls.vecino = Neighbor.objects.create(
            identifier="11.111.111-1", full_name="María González",
        )

        cls.att_funcionario_d1 = Attention.objects.create(
            neighbor=cls.vecino, delegation=cls.d1,
            attention_type=cls.tipo, attention_subtype=cls.sub,
            description="Solicitud de ayuda social para el grupo familiar.",
            responsible=cls.funcionario.user,
        )
        cls.att_d1 = Attention.objects.create(
            neighbor=cls.vecino, delegation=cls.d1,
            attention_type=cls.tipo, attention_subtype=cls.sub,
            description="Segunda atención de la delegación Centro.",
            responsible=cls.otro_funcionario.user,
        )
        cls.att_d2 = Attention.objects.create(
            neighbor=cls.vecino, delegation=cls.d2,
            attention_type=cls.tipo, attention_subtype=cls.sub,
            description="Atención de la delegación Avenida del Mar.",
            responsible=cls.otro_funcionario.user,
        )

    def _login(self, username):
        self.client.logout()
        assert self.client.login(username=username, password=DEMO_PASSWORD)

    def _numbers_shown(self, resp):
        return [row["cells"][0]["text"] for row in resp.context["rows"]]

    def _post_data(self, **extra):
        data = {
            "neighbor": str(self.vecino.pk),
            "delegation": str(self.d1.pk),
            "attention_type": str(self.tipo.pk),
            "attention_subtype": str(self.sub.pk),
            "description": "Descripción válida de la atención ingresada.",
        }
        data.update(extra)
        return data

    # ---------------------------------------------------------------
    # Alcance por rol
    # ---------------------------------------------------------------

    def test_listado_funcionario_solo_propias(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._numbers_shown(resp), [self.att_funcionario_d1.number])

    def test_listado_delegado_solo_su_delegacion(self):
        self._login("delegado")
        resp = self.client.get(reverse("attentions"))
        numbers = self._numbers_shown(resp)
        self.assertIn(self.att_funcionario_d1.number, numbers)
        self.assertIn(self.att_d1.number, numbers)
        self.assertNotIn(self.att_d2.number, numbers)

    def test_listado_coordinador_segun_delegacion_activa(self):
        self._login("coordinador")
        resp = self.client.get(reverse("attentions"))
        numbers = self._numbers_shown(resp)
        self.assertIn(self.att_funcionario_d1.number, numbers)
        self.assertIn(self.att_d1.number, numbers)
        self.assertNotIn(self.att_d2.number, numbers)

    def test_listado_superadmin_ve_todas(self):
        self._login("superadmin")
        resp = self.client.get(reverse("attentions"))
        numbers = self._numbers_shown(resp)
        for att in (self.att_funcionario_d1, self.att_d1, self.att_d2):
            self.assertIn(att.number, numbers)

    def test_aviso_de_alcance_en_listado(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions"))
        self.assertContains(resp, "solo las atenciones que ingresaste tú")

    # ---------------------------------------------------------------
    # Consulta y edición con alcance (403 / 404)
    # ---------------------------------------------------------------

    def test_funcionario_no_abre_atencion_ajena(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions_detail", args=[self.att_d1.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_funcionario_no_edita_atencion_ajena(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions_edit", args=[self.att_d1.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_atencion_inexistente_404(self):
        self._login("superadmin")
        resp = self.client.get(reverse("attentions_detail", args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_delegado_ve_consulta_de_su_delegacion(self):
        self._login("delegado")
        resp = self.client.get(reverse("attentions_detail", args=[self.att_d1.pk]))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse("attentions_detail", args=[self.att_d2.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_delegado_edita_atencion_de_su_delegacion(self):
        self._login("delegado")
        resp = self.client.get(reverse("attentions_edit", args=[self.att_d1.pk]))
        self.assertEqual(resp.status_code, 200)

    # ---------------------------------------------------------------
    # POST manipulado rechazado
    # ---------------------------------------------------------------

    def test_post_delegacion_no_permitida(self):
        # El coordinador solo tiene autorizadas DEL01 y DEL02; DEL03 no es
        # una opción válida en su formulario, así que se rechaza.
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(delegation=str(self.d3.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attention.objects.count(), 3)

    def test_post_delegacion_ignorada_para_delegado(self):
        # El delegado tiene delegación fija: el servidor ignora lo que llegue
        # por POST y la atención queda en su delegación (DEL01).
        self._login("delegado")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(delegation=str(self.d2.pk)),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Attention.objects.count(), 4)
        nueva = Attention.objects.latest("pk")
        self.assertEqual(nueva.delegation_id, self.d1.pk)

    def test_post_delegacion_inactiva(self):
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(delegation=str(self.d_inactiva.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attention.objects.count(), 3)

    def test_post_tipo_inactivo(self):
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(attention_type=str(self.tipo_inactivo.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attention.objects.count(), 3)

    def test_post_subtipo_de_otro_tipo(self):
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(attention_subtype=str(self.sub_otro_tipo.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attention.objects.count(), 3)

    def test_post_subtipo_inactivo(self):
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(attention_subtype=str(self.sub_inactivo.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attention.objects.count(), 3)

    def test_post_solicitante_inexistente(self):
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(neighbor="999999"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "solicitante")
        self.assertEqual(Attention.objects.count(), 3)

    def test_post_descripcion_corta(self):
        self._login("coordinador")
        resp = self.client.post(
            reverse("attentions_new"), self._post_data(description="corta"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "al menos 10 caracteres")
        self.assertEqual(Attention.objects.count(), 3)

    # ---------------------------------------------------------------
    # Crear correcto, número automático y único
    # ---------------------------------------------------------------

    def test_crear_atencion_numero_automatico(self):
        self._login("coordinador")
        resp = self.client.post(reverse("attentions_new"), self._post_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Attention.objects.count(), 4)
        nueva = Attention.objects.latest("pk")
        self.assertRegex(nueva.number, r"^ATN-\d{4}$")

    def test_doble_envio_no_registra_dos(self):
        # Un único POST válido crea exactamente una atención y el número queda
        # único; el botón se deshabilita en el cliente (sgr.js) para no repetir.
        self._login("coordinador")
        self.client.post(reverse("attentions_new"), self._post_data())
        self.assertEqual(Attention.objects.count(), 4)
        numbers = list(Attention.objects.values_list("number", flat=True))
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_form_create_muestra_responsable_y_fecha_automatica(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions_new"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Responsable:")
        self.assertContains(resp, "automáticas")

    def test_form_editar_muestra_estado_editable(self):
        self._login("delegado")
        resp = self.client.get(reverse("attentions_edit", args=[self.att_d1.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Estado")
        self.assertContains(resp, "Ingresada")

    # ---------------------------------------------------------------
    # Endpoint JSON de solicitantes
    # ---------------------------------------------------------------

    def test_solicitantes_exige_sesion(self):
        resp = self.client.get(reverse("attention_neighbors"), {"q": "María"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])

    def test_solicitantes_exige_permiso(self):
        sin_rol = make_user("sinrol", password=DEMO_PASSWORD)
        self.client.login(username="sinrol", password=DEMO_PASSWORD)
        resp = self.client.get(reverse("attention_neighbors"), {"q": "María"})
        self.assertEqual(resp.status_code, 403)

    def test_solicitantes_devuelve_json(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attention_neighbors"), {"q": "María"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"][0]["pk"], self.vecino.pk)

    # ---------------------------------------------------------------
    # Cambio de delegación activa y exportación
    # ---------------------------------------------------------------

    def test_cambio_delegacion_activa_cambia_listado(self):
        self._login("coordinador")
        resp = self.client.post(reverse("switch_delegation"), {"delegation": str(self.d2.pk)})
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse("attentions"))
        numbers = self._numbers_shown(resp)
        self.assertIn(self.att_d2.number, numbers)
        self.assertNotIn(self.att_d1.number, numbers)

    def test_exportacion_respeta_alcance_y_filtros(self):
        self._login("coordinador")
        resp = self.client.get(reverse("attentions_export"))
        sheet = load_workbook(filename=io.BytesIO(resp.content)).active
        self.assertEqual(
            [cell.value for cell in sheet[1]],
            ["N°", "Fecha y hora", "Solicitante", "Tipo", "Sub atención",
             "Delegación", "Responsable", "Estado"],
        )
        # Delegación activa DEL01: 2 filas de datos.
        self.assertEqual(sheet.max_row - 1, 2)

    def test_exportacion_respeta_filtro_estado(self):
        self._login("superadmin")
        resp = self.client.get(reverse("attentions_export"), {"estado": "received"})
        sheet = load_workbook(filename=io.BytesIO(resp.content)).active
        self.assertEqual(sheet.max_row - 1, 3)

    def test_exportacion_funcionario_solo_propias(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions_export"))
        sheet = load_workbook(filename=io.BytesIO(resp.content)).active
        self.assertEqual(sheet.max_row - 1, 1)
