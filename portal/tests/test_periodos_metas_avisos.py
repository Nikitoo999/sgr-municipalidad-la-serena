"""Períodos y cierre de trimestre, metas por cargo, avisos y alertas (Unidad 3)."""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones import periodos as reglas
from operaciones.calculos import razon_tubo, resumen_equipo
from operaciones.models import Attention, Neighbor, Notice, TubeEntry
from portal.tests.helpers import (
    DEMO_PASSWORD, TEST_STORAGES, ensure_roles, make_delegation, make_employee, make_user,
)
from sgr_core.models import (
    AttentionSubtype, AttentionType, Period, Position, PositionItemGoal, ProjectItem,
)


class PeriodBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        make_user("superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True)
        cls.coord = make_employee("coord", "10.000.003-3", cls.d1, cls.roles["ROL02"])
        cls.coord.authorized_delegations.set([cls.d1])
        cls.delegado = make_employee("delegado", "10.000.004-4", cls.d1, cls.roles["ROL03"])
        cls.ana = make_employee("ana", "10.000.001-1", cls.d1, cls.roles["ROL04"], first_name="Ana", last_name="Pérez")
        cls.t3 = Period.objects.create(name="Trimestre Jul-Sep 2026", start_date=date(2026, 7, 1),
                                       end_date=date(2026, 9, 30), quarter=3)
        cls.t4 = Period.objects.create(name="Trimestre Oct-Dic 2026", start_date=date(2026, 10, 1),
                                       end_date=date(2026, 12, 31), quarter=4)

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=DEMO_PASSWORD))


@override_settings(STORAGES=TEST_STORAGES)
class CierreTrimestreTests(PeriodBase):
    def crear_pendientes(self):
        abierta = TubeEntry.objects.create(delegation=self.d1, title="Poda", requester="JJVV",
                                           responsible=self.ana, request_date=date(2026, 9, 10))
        hecha = TubeEntry.objects.create(delegation=self.d1, title="Bache", requester="JJVV",
                                         responsible=self.ana, request_date=date(2026, 9, 11), status="done")
        tipo = AttentionType.objects.create(code="TAT01", name="Social")
        sub = AttentionSubtype.objects.create(code="SAT01", name="Ayuda", attention_type=tipo)
        vecino = Neighbor.objects.create(identifier="16.000.001-6", full_name="María González", phone="+56911111111")
        atencion = Attention.objects.create(neighbor=vecino, delegation=self.d1, attention_type=tipo,
                                            attention_subtype=sub, description="Pendiente del T3",
                                            responsible=self.ana.user)
        Attention.objects.filter(pk=atencion.pk).update(
            created_at=timezone.make_aware(timezone.datetime(2026, 9, 15, 10, 0)))
        return abierta, hecha, atencion

    def test_cerrar_traspasa_con_prioridad_y_avisa(self):
        abierta, hecha, atencion = self.crear_pendientes()
        resultado = reglas.cerrar_trimestre(self.t3, self.t4, None)
        self.assertEqual((resultado["tubos"], resultado["atenciones"]), (1, 1))
        abierta.refresh_from_db(); hecha.refresh_from_db(); atencion.refresh_from_db(); self.t3.refresh_from_db()
        self.assertTrue(abierta.priority)
        self.assertEqual(abierta.carried_to_period, self.t4)
        self.assertTrue(abierta.history.filter(kind="priority").exists())
        self.assertFalse(hecha.priority)
        self.assertTrue(atencion.priority)
        self.assertEqual(self.t3.status, "Cerrado")
        self.assertEqual(Notice.objects.filter(delegation=self.d1, kind="transfer").count(), 1)
        # El tubo traspasado cuenta en el trimestre de destino (0 de 1 realizadas).
        self.assertEqual(razon_tubo(self.ana, self.t4), Decimal("0"))

    def test_no_se_cierra_dos_veces(self):
        reglas.cerrar_trimestre(self.t3, self.t4, None)
        with self.assertRaises(ValueError):
            reglas.cerrar_trimestre(self.t3, self.t4, None)

    def test_coordinador_ve_pero_no_cierra(self):
        self.login("coord")
        self.assertEqual(self.client.get(reverse("period_close")).status_code, 200)
        resp = self.client.post(reverse("period_close"), {"periodo": self.t3.pk, "confirmar": "1"})
        self.assertEqual(resp.status_code, 403)

    def test_superadmin_cierra_y_crea_el_siguiente(self):
        self.crear_pendientes()
        self.login("superadmin")
        self.t4.delete()  # sin trimestre siguiente: se crea al cerrar
        self.client.post(reverse("period_close"), {"periodo": self.t3.pk, "destino": "nuevo", "confirmar": "1"})
        nuevo = Period.objects.get(name="Trimestre Oct-Dic 2026")
        self.assertEqual((nuevo.start_date, nuevo.end_date, nuevo.quarter), (date(2026, 10, 1), date(2026, 12, 31), 4))
        self.assertEqual(Period.objects.get(pk=self.t3.pk).status, "Cerrado")

    def test_reabrir_exige_motivo(self):
        reglas.cerrar_trimestre(self.t3, self.t4, None)
        self.login("superadmin")
        self.client.post(reverse("period_close"), {"accion": "reabrir", "periodo": self.t3.pk, "motivo": "corto"})
        self.assertEqual(Period.objects.get(pk=self.t3.pk).status, "Cerrado")
        self.client.post(reverse("period_close"), {"accion": "reabrir", "periodo": self.t3.pk,
                                                   "motivo": "Autorizado por coordinación para corregir metas"})
        self.assertEqual(Period.objects.get(pk=self.t3.pk).status, "En curso")

    def test_formulario_de_periodo(self):
        self.login("superadmin")
        resp = self.client.post(reverse("periods_new"), {"name": "Malo", "start_date": "2027-03-31", "end_date": "2027-01-01"})
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse("periods_new"), {"name": "Cruzado", "start_date": "2026-12-01", "end_date": "2027-02-28"})
        self.assertEqual(resp.status_code, 200)
        self.client.post(reverse("periods_new"), {"name": "Trimestre Ene-Mar 2027", "start_date": "2027-01-01", "end_date": "2027-03-31"})
        nuevo = Period.objects.get(name="Trimestre Ene-Mar 2027")
        self.assertEqual((nuevo.quarter, nuevo.status, nuevo.business_days), (1, "En curso", 64))

    def test_periodo_cerrado_no_se_edita(self):
        reglas.cerrar_trimestre(self.t3, self.t4, None)
        self.login("superadmin")
        resp = self.client.post(reverse("periods_edit", args=[self.t3.pk]),
                                {"name": "Otro nombre", "start_date": "2026-07-01", "end_date": "2026-09-30"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Period.objects.get(pk=self.t3.pk).name, "Trimestre Jul-Sep 2026")


@override_settings(STORAGES=TEST_STORAGES)
class MetasPorCargoTests(PeriodBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        cls.i1 = ProjectItem.objects.create(code="MTX01", name="Atención social")
        cls.i2 = ProjectItem.objects.create(code="MTX02", name="Visita en terreno")
        cls.g1 = PositionItemGoal.objects.create(position=cls.cargo, item=cls.i1, period=cls.t3, weight=60, target_value=90)

    def url(self, period):
        return reverse("position_goals", args=[self.cargo.pk]) + f"?periodo={period.pk}"

    def test_suma_distinta_de_100_se_rechaza_salvo_excepcion(self):
        self.login("superadmin")
        datos = {"periodo": self.t3.pk, f"weight_{self.g1.pk}": "60", f"target_{self.g1.pk}": "90",
                 "new_item_0": self.i2.pk, "new_weight_0": "30", "new_target_0": "12"}
        self.client.post(self.url(self.t3), datos)
        self.assertEqual(PositionItemGoal.objects.filter(position=self.cargo, period=self.t3).count(), 1)
        self.client.post(self.url(self.t3), {**datos, "excepcion": "1", "motivo_excepcion": "El Excel municipal suma 90 %"})
        self.assertEqual(PositionItemGoal.objects.filter(position=self.cargo, period=self.t3).count(), 2)

    def test_suma_100_se_guarda(self):
        self.login("superadmin")
        self.client.post(self.url(self.t3), {"periodo": self.t3.pk, f"weight_{self.g1.pk}": "70",
                                             f"target_{self.g1.pk}": "80", "new_item_0": self.i2.pk,
                                             "new_weight_0": "30", "new_target_0": "12"})
        self.g1.refresh_from_db()
        self.assertEqual((self.g1.weight, self.g1.target_value), (70, 80))

    def test_copiar_metas_y_periodo_cerrado(self):
        self.login("superadmin")
        self.client.post(self.url(self.t4), {"periodo": self.t4.pk, "accion": "copiar"})
        self.assertEqual(PositionItemGoal.objects.filter(position=self.cargo, period=self.t4).count(), 1)
        reglas.cerrar_trimestre(self.t3, self.t4, None)
        self.client.post(self.url(self.t3), {"periodo": self.t3.pk, f"weight_{self.g1.pk}": "100",
                                             f"target_{self.g1.pk}": "1"})
        self.g1.refresh_from_db()
        self.assertEqual(self.g1.weight, 60)

    def test_coordinador_consulta_pero_no_edita(self):
        self.login("coord")
        self.assertEqual(self.client.get(self.url(self.t3)).status_code, 200)
        self.client.post(self.url(self.t3), {"periodo": self.t3.pk, f"weight_{self.g1.pk}": "100",
                                             f"target_{self.g1.pk}": "1"})
        self.g1.refresh_from_db()
        self.assertEqual(self.g1.weight, 60)


@override_settings(STORAGES=TEST_STORAGES)
class AvisosYAlertasTests(PeriodBase):
    def test_aviso_cuenta_en_la_campana_y_se_marca_leido(self):
        Notice.objects.create(kind="transfer", title="Traspaso de prueba", delegation=self.d1)
        self.login("delegado")
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.context["sgr_badge_count"], 1)
        self.client.post(reverse("notices_mark_read"))
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.context["sgr_badge_count"], 0)

    def test_alerta_de_compromiso_vencido_y_revision(self):
        hoy = timezone.localdate()
        TubeEntry.objects.create(delegation=self.d1, title="Vencida", requester="JJVV", responsible=self.ana,
                                 request_date=hoy - timedelta(days=20), due_date=hoy - timedelta(days=2))
        self.login("delegado")
        pagina = self.client.get(reverse("notices"))
        self.assertContains(pagina, "Compromiso vencido")
        key = pagina.context["pendientes"][0].key
        self.client.post(reverse("alert_review"), {"key": key})
        pagina = self.client.get(reverse("notices"))
        self.assertEqual([a.key for a in pagina.context["revisadas"]], [key])

    def test_resumen_de_equipo(self):
        cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        delegado_cargo = Position.objects.create(code="CAR01", name="Delegado", is_evaluated=False)

        class Emp:
            def __init__(self, position):
                self.position = position
                self.position_id = position.pk

        item = ProjectItem.objects.create(code="MTX01", name="Atención social")
        filas = [
            {"empleado": Emp(cargo), "cumplimiento": {"items": [{"item": item, "razon": Decimal("0.5")}],
                                                     "porcentaje": Decimal("50"), "esperado": Decimal("0.8"),
                                                     "semaforo": "amarillo"}},
            {"empleado": Emp(delegado_cargo), "cumplimiento": {"items": [{"item": item, "razon": Decimal("1")}],
                                                              "porcentaje": Decimal("100"), "esperado": Decimal("0.8"),
                                                              "semaforo": "verde"}},
        ]
        equipo = resumen_equipo(filas)
        self.assertEqual(equipo["evaluados"], 1)  # el Delegado no se evalúa
        self.assertEqual(equipo["porcentaje"], Decimal("50.00"))
        self.assertEqual(equipo["items_a_reforzar"][0]["logro_pct"], Decimal("50.0"))

    def test_funcionario_ve_sus_registros_observados(self):
        from operaciones.models import Attention as A

        tipo = AttentionType.objects.create(code="TAT01", name="Social")
        sub = AttentionSubtype.objects.create(code="SAT01", name="Ayuda", attention_type=tipo)
        vecino = Neighbor.objects.create(identifier="16.000.001-6", full_name="María González", phone="+56911111111")
        A.objects.create(neighbor=vecino, delegation=self.d1, attention_type=tipo, attention_subtype=sub,
                         description="Observada", responsible=self.ana.user,
                         validation_status="rejected", validation_notes="Falta foto")
        self.login("ana")
        pagina = self.client.get(reverse("notices"))
        self.assertContains(pagina, "Atención observada")
        self.assertContains(pagina, "Falta foto")



@override_settings(STORAGES=TEST_STORAGES)
class AuditoriaTests(PeriodBase):
    def test_edicion_guarda_valor_anterior_y_nuevo(self):
        import json

        from portal.models import AuditLog

        self.login("superadmin")
        self.client.post(reverse("delegations_edit", args=[self.d1.pk]), {
            "name": "Centro Histórico", "commune": "La Serena", "address": "", "color": "#C62828", "status": "Activa",
        })
        evento = AuditLog.objects.filter(action="edit", module="delegations").latest("pk")
        cambios = json.loads(evento.changes)
        self.assertIn({"campo": "Nombre de la delegación", "anterior": "Centro", "nuevo": "Centro Histórico"}, cambios)
        pagina = self.client.get(reverse("audit_log"), {"modulo": "delegations"})
        self.assertContains(pagina, "Centro → Centro Histórico")

    def test_solo_superadmin_ve_la_auditoria(self):
        self.login("coord")
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 403)
