"""Pruebas de las mejoras de la Unidad 3.

- Ventana emergente (modal) para "Nuevo ...": ``?modal=1`` en el formulario.
- Nuevo requerimiento de la matriz SGR:
  punto 4 (cierre automático de la semana desde el martes siguiente),
  punto 5 (gestiones preparatorias no suman puntaje),
  punto 8 (felicitaciones las registra el delegado o superior),
  punto 9 (días libres registrados por el delegado en el semáforo).
- Mantenedor de Organizaciones comunitarias.
"""

from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones import rules
from operaciones.models import Attention, EmployeeDayOff, EmployeeFeedback, Neighbor
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee, make_user,
)
from sgr_core.models import (
    AttentionSubtype, AttentionType, CommunityOrganization, Delegation, Position, Role,
    RolePermission,
)


class AutoClosureRuleTests(SimpleTestCase):
    """Punto 4: la semana (lunes a viernes) se completa hasta el lunes siguiente."""

    def test_lunes_siguiente_todavia_abierta(self):
        miercoles = date(2026, 11, 11)
        self.assertFalse(rules.is_auto_closed(miercoles, today=date(2026, 11, 16)))

    def test_martes_siguiente_queda_cerrada(self):
        miercoles = date(2026, 11, 11)
        self.assertTrue(rules.is_auto_closed(miercoles, today=date(2026, 11, 17)))

    def test_semana_en_curso_abierta(self):
        hoy = date(2026, 11, 23)
        self.assertFalse(rules.is_auto_closed(hoy, today=hoy))

    def test_mensaje_de_ingreso_fuera_de_plazo(self):
        msg = rules.past_week_entry_error(date(2026, 11, 3), today=date(2026, 11, 17))
        self.assertIn("02-11-2026 al 08-11-2026", msg)
        self.assertEqual(rules.past_week_entry_error(date(2026, 11, 10), today=date(2026, 11, 16)), "")


@override_settings(STORAGES=TEST_STORAGES)
class AttentionRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.coordinador = make_employee("coordinador", "11.111.199-9", cls.d1, cls.roles["ROL02"])
        cls.coordinador.authorized_delegations.set([cls.d1])
        cls.tipo = AttentionType.objects.create(code="TAT01", name="Social")
        cls.sub = AttentionSubtype.objects.create(code="SAT01", name="Taller realizado", attention_type=cls.tipo)
        cls.sub_prep = AttentionSubtype.objects.create(
            code="SAT02", name="Coordinación de taller", attention_type=cls.tipo, scores=False,
        )
        cls.vecino = Neighbor.objects.create(identifier="11.111.111-1", full_name="María González")

    def setUp(self):
        self.client.login(username="coordinador", password=DEMO_PASSWORD)

    def datos(self, sub):
        return {
            "neighbor_rut": self.vecino.identifier, "neighbor_name": self.vecino.full_name,
            "neighbor_phone": "+56 9 1111 1111", "delegation": str(self.d1.pk),
            "attention_type": str(self.tipo.pk), "attention_subtype": str(sub.pk),
            "description": "Descripción válida de la atención ingresada.",
        }

    def test_gestion_preparatoria_no_suma(self):
        self.client.post(reverse("attentions_new"), self.datos(self.sub_prep))
        atencion = Attention.objects.get()
        self.assertFalse(atencion.counts_for_score)
        self.assertEqual(atencion.score_display, "No cuenta (gestión preparatoria)")

    def test_accion_realizada_si_suma(self):
        self.client.post(reverse("attentions_new"), self.datos(self.sub))
        self.assertTrue(Attention.objects.get().counts_for_score)

    def test_cambiar_a_subtipo_preparatorio_recalcula(self):
        self.client.post(reverse("attentions_new"), self.datos(self.sub))
        atencion = Attention.objects.get()
        datos = self.datos(self.sub_prep)
        datos["status"] = "received"
        self.client.post(reverse("attentions_edit", args=[atencion.pk]), datos)
        atencion.refresh_from_db()
        self.assertEqual(atencion.attention_subtype_id, self.sub_prep.pk)
        self.assertFalse(atencion.counts_for_score)

    def test_atencion_de_semana_vencida_queda_bloqueada(self):
        atencion = Attention.objects.create(
            neighbor=self.vecino, delegation=self.d1, attention_type=self.tipo,
            attention_subtype=self.sub, description="Atención antigua de prueba.",
            responsible=self.coordinador.user,
        )
        hace_dos_semanas = timezone.now() - timedelta(days=14)
        Attention.objects.filter(pk=atencion.pk).update(created_at=hace_dos_semanas)
        atencion.refresh_from_db()
        cierre = rules.attention_closure(atencion)
        self.assertIsNotNone(cierre)
        self.assertTrue(getattr(cierre, "automatic", False))
        resp = self.client.get(reverse("attentions_edit", args=[atencion.pk]))
        self.assertRedirects(resp, reverse("attentions_detail", args=[atencion.pk]),
                             fetch_redirect_response=False)
        self.assertIn((self.d1.pk, rules.week_start(rules.local_day(hace_dos_semanas))),
                      rules.closed_pairs([atencion]))


@override_settings(STORAGES=TEST_STORAGES)
class ModalCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_roles()
        make_user("superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)

    def setUp(self):
        self.client.login(username="superadmin", password=DEMO_PASSWORD)

    def test_listado_abre_nuevo_en_modal(self):
        resp = self.client.get(reverse("delegations"))
        self.assertContains(resp, 'data-sgr-modal data-modal-title="Nueva delegación"')

    def test_formulario_en_modal_sin_cabecera_y_enmarcable(self):
        resp = self.client.get(reverse("delegations_new"), {"modal": "1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(resp, 'class="embed"')
        self.assertNotContains(resp, 'id="side"')
        self.assertNotContains(resp, 'id="chatWidget"')

    def test_pagina_normal_sigue_igual(self):
        resp = self.client.get(reverse("delegations_new"))
        self.assertEqual(resp["X-Frame-Options"], "DENY")
        self.assertContains(resp, 'id="side"')

    def test_guardar_en_modal_avisa_y_no_redirige(self):
        resp = self.client.post(
            reverse("delegations_new") + "?modal=1",
            {"name": "Rural Norte", "commune": "La Serena", "address": "", "color": "#920000", "status": "Activa"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "sgr-modal-redirect")
        self.assertTrue(Delegation.objects.filter(name="Rural Norte").exists())
        # El mensaje de éxito queda en la sesión para el listado que se recarga.
        listado = self.client.get(reverse("delegations"))
        self.assertContains(listado, "creada correctamente")

    def test_errores_se_muestran_dentro_del_modal(self):
        resp = self.client.post(reverse("delegations_new") + "?modal=1", {"name": "", "status": "Activa"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "sgr-modal-redirect")
        self.assertContains(resp, 'class="embed"')


@override_settings(STORAGES=TEST_STORAGES)
class ComplianceRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.delegado = make_employee("delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"])
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, cls.roles["ROL04"], first_name="Ana")
        cls.ana.position = Position.objects.create(code="CAR02", name="Gestor Social")
        cls.ana.save()
        # Rol personalizado de alcance "registros propios" con permiso de crear en Cumplimiento.
        rol = Role.objects.create(code="ROL09", name="Funcionario ampliado", scope="own_records")
        for accion in ("view", "create"):
            RolePermission.objects.create(role=rol, module="achievements", action=accion)
        cls.ampliado = make_employee("ampliado", "10.000.002-2", cls.d1, rol)

    def test_delegado_registra_dia_libre(self):
        self.client.login(username="delegado", password=DEMO_PASSWORD)
        resp = self.client.post(reverse("day_off_create", args=[self.ana.pk]), {
            "kind": "administrative", "start_date": "2026-11-16", "end_date": "2026-11-17", "notes": "",
        })
        self.assertRedirects(resp, reverse("achievements"), fetch_redirect_response=False)
        registro = EmployeeDayOff.objects.get(employee=self.ana)
        self.assertEqual(registro.business_days, 2)
        self.assertEqual(registro.registered_by, self.delegado.user)

    def test_dia_libre_con_fechas_invertidas_se_rechaza(self):
        self.client.login(username="delegado", password=DEMO_PASSWORD)
        self.client.post(reverse("day_off_create", args=[self.ana.pk]), {
            "kind": "vacation", "start_date": "2026-11-20", "end_date": "2026-11-16",
        })
        self.assertFalse(EmployeeDayOff.objects.exists())

    def test_funcionario_no_registra_dia_libre(self):
        self.client.login(username="ana", password=DEMO_PASSWORD)
        resp = self.client.post(reverse("day_off_create", args=[self.ana.pk]), {
            "kind": "vacation", "start_date": "2026-11-16", "end_date": "2026-11-16",
        })
        self.assertEqual(resp.status_code, 403)

    def test_rol_de_funcionario_con_permiso_no_registra_felicitacion(self):
        self.client.login(username="ampliado", password=DEMO_PASSWORD)
        resp = self.client.post(reverse("feedback_create", args=[self.ana.pk]), {
            "kind": "complaint", "date": "2026-11-16", "description": "x",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(EmployeeFeedback.objects.exists())


@override_settings(STORAGES=TEST_STORAGES)
class OrganizationsCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")
        make_user("superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.delegado = make_employee("delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"])
        cls.funcionario = make_employee("funcionario", "11.111.113-3", cls.d1, cls.roles["ROL04"])
        cls.org1 = CommunityOrganization.objects.create(
            name="JUNTA DE VECINOS VILLA EL SOL", category="neighborhood", delegation=cls.d1,
            registry_number="1234",
        )
        cls.org2 = CommunityOrganization.objects.create(
            name="CLUB ADULTO MAYOR LOS AROMOS", category="senior", delegation=cls.d2,
        )

    def login(self, username):
        self.client.login(username=username, password=DEMO_PASSWORD)

    def test_superadmin_ve_todas(self):
        self.login("superadmin")
        resp = self.client.get(reverse("organizations"))
        self.assertContains(resp, "VILLA EL SOL")
        self.assertContains(resp, "LOS AROMOS")

    def test_delegado_solo_ve_su_delegacion(self):
        self.login("delegado")
        resp = self.client.get(reverse("organizations"))
        self.assertContains(resp, "VILLA EL SOL")
        self.assertNotContains(resp, "LOS AROMOS")
        self.assertEqual(self.client.get(reverse("organizations_detail", args=[self.org2.pk])).status_code, 403)

    def test_delegado_crea_en_su_delegacion(self):
        self.login("delegado")
        resp = self.client.post(reverse("organizations_new"), {
            "name": "  club deportivo   unión centro ", "category": "sports",
            "delegation": str(self.d1.pk), "status": "Activo",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(CommunityOrganization.objects.filter(name="CLUB DEPORTIVO UNIÓN CENTRO").exists())

    def test_delegado_no_crea_en_otra_delegacion(self):
        self.login("delegado")
        self.client.post(reverse("organizations_new"), {
            "name": "Comité de seguridad", "category": "committee",
            "delegation": str(self.d2.pk), "status": "Activo",
        })
        self.assertFalse(CommunityOrganization.objects.filter(name__icontains="seguridad").exists())

    def test_registro_pj_duplicado_se_rechaza(self):
        self.login("superadmin")
        self.client.post(reverse("organizations_new"), {
            "name": "Otra organización", "category": "other", "registry_number": "1234", "status": "Activo",
        })
        self.assertFalse(CommunityOrganization.objects.filter(name="OTRA ORGANIZACIÓN").exists())

    def test_funcionario_solo_consulta(self):
        self.login("funcionario")
        self.assertEqual(self.client.get(reverse("organizations")).status_code, 200)
        self.assertEqual(self.client.get(reverse("organizations_new")).status_code, 403)

    def test_filtro_por_categoria_y_exportacion(self):
        self.login("superadmin")
        resp = self.client.get(reverse("organizations"), {"categoria": "senior"})
        self.assertContains(resp, "LOS AROMOS")
        self.assertNotContains(resp, "VILLA EL SOL")
        export = self.client.get(reverse("organizations_export"), {"categoria": "senior"})
        self.assertEqual(export.status_code, 200)
        self.assertIn("spreadsheetml", export["Content-Type"])


@override_settings(STORAGES=TEST_STORAGES)
class CorreccionesCriticasTests(TestCase):
    """Errores reportados por el equipo al probar la rama (regresiones)."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        make_user("superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, cls.roles["ROL04"],
                                first_name="Ana", last_name="Pérez")
        cls.ana.position = cls.cargo
        cls.ana.save()

    def setUp(self):
        self.client.login(username="superadmin", password=DEMO_PASSWORD)

    def test_organigrama_dibuja_funcionarios_en_el_html(self):
        # Antes salía vacío: el defaultdict anidado hacía que la plantilla
        # resolviera posiciones.items como una lista vacía.
        resp = self.client.get(reverse("organigrama"))
        self.assertContains(resp, "Ana Pérez")
        self.assertContains(resp, "DEL01 · Centro")
        self.assertContains(resp, "Gestor Social (1)")
        self.assertContains(resp, "Funcionario")  # nombre del rol, no el código de alcance

    def test_reenviar_codigo_por_get_no_da_error(self):
        resp = self.client.get(reverse("password_reset_resend"))
        self.assertRedirects(resp, reverse("password_reset_verify"), fetch_redirect_response=False)

    def test_las_ventanas_ocultas_respetan_hidden(self):
        # Sin esta regla, display:grid anula [hidden] y las ventanas del Tubo y
        # de Cumplimiento aparecen abiertas sin poder cerrarse.
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "portal/static/portal/css/sgr.css").read_text(encoding="utf-8")
        self.assertIn(".smodal-backdrop[hidden]{display:none}", css)


@override_settings(STORAGES=TEST_STORAGES)
class DirectivaOrganizacionTests(TestCase):
    """Organigrama de la organización (preview de implementación)."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")
        cls.delegado = make_employee("delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"])
        cls.funcionario = make_employee("funcionario", "11.111.113-3", cls.d1, cls.roles["ROL04"])
        cls.org = CommunityOrganization.objects.create(name="JJVV VILLA EL FARO", delegation=cls.d1)
        cls.org_ajena = CommunityOrganization.objects.create(name="CLUB DEL MAR", delegation=cls.d2)

    def test_cargos_base_creados_por_migracion(self):
        from sgr_core.models import DirectiveRole

        self.assertEqual(
            list(DirectiveRole.objects.filter(is_base=True).values_list("name", flat=True)),
            ["Presidente/a", "Secretario/a", "Tesorero/a"],
        )

    def test_asignar_y_reemplazar_integrante(self):
        from sgr_core.models import DirectiveRole, OrganizationMember

        presidente = DirectiveRole.objects.get(name="Presidente/a")
        self.client.login(username="delegado", password=DEMO_PASSWORD)
        url = reverse("organization_member_save", args=[self.org.pk])
        self.client.post(url, {"role": presidente.pk, "full_name": "Patricia Soto", "phone": "+56 9 8412 3310"})
        self.client.post(url, {"role": presidente.pk, "full_name": "Rodrigo Vera"})
        vigentes = OrganizationMember.alive.filter(organization=self.org)
        self.assertEqual([m.full_name for m in vigentes], ["Rodrigo Vera"])
        detalle = self.client.get(reverse("organizations_detail", args=[self.org.pk]))
        self.assertContains(detalle, "Organigrama · JJVV VILLA EL FARO")
        self.assertContains(detalle, "Rodrigo Vera")

    def test_no_se_edita_directiva_de_otra_delegacion(self):
        from sgr_core.models import DirectiveRole

        self.client.login(username="delegado", password=DEMO_PASSWORD)
        resp = self.client.post(reverse("organization_member_save", args=[self.org_ajena.pk]), {
            "role": DirectiveRole.objects.first().pk, "full_name": "Intruso Total",
        })
        self.assertEqual(resp.status_code, 403)

    def test_funcionario_no_edita_directiva(self):
        from sgr_core.models import DirectiveRole

        self.client.login(username="funcionario", password=DEMO_PASSWORD)
        resp = self.client.post(reverse("organization_member_save", args=[self.org.pk]), {
            "role": DirectiveRole.objects.first().pk, "full_name": "Sin Permiso",
        })
        self.assertEqual(resp.status_code, 403)

    def test_crear_cargo_directivo(self):
        from sgr_core.models import DirectiveRole

        self.client.login(username="delegado", password=DEMO_PASSWORD)
        self.client.post(reverse("directive_role_create"), {"name": "Vicepresidente/a"})
        self.assertTrue(DirectiveRole.objects.filter(name="Vicepresidente/a").exists())
