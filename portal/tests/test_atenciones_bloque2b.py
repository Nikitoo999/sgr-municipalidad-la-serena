"""Pruebas del Bloque 2B: módulo de Atención ampliado.

Cubre:
- 2.5 RUT (validado), nombre completo y teléfono obligatorios al ingresar; el
  vecino se reutiliza por RUT o se registra; "Requiere visita".
- 2.6 Estado "Sin resolver" con motivo obligatorio; hasta 3 gestiones de
  seguimiento por atención, que no puntúan como atención nueva.
- 2.7 Tope de 7 ingresos por funcionario y día; cierre semanal por delegación
  (bloquea ingreso y edición; reabrir solo superadmin/coordinador) y los
  ingresos del rol Delegado no suman al puntaje operativo.
"""

import importlib
import io
from datetime import timedelta

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from operaciones import rules
from operaciones.models import Attention, AttentionFollowUp, Neighbor, WeeklyClosure
from portal.models import AuditLog
from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
    make_user,
)
from sgr_core.models import AttentionSubtype, AttentionType


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", color="#1D6FA5")
        cls.superadmin = make_user(
            "superadmin", password=DEMO_PASSWORD, is_superuser=True, is_staff=True,
        )
        cls.coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, cls.roles["ROL02"],
            first_name="Carla", last_name="Coordina",
        )
        cls.coordinador.authorized_delegations.set([cls.d1, cls.d2])
        cls.delegado = make_employee(
            "delegado", "11.111.112-2", cls.d1, cls.roles["ROL03"],
            first_name="Diego", last_name="Delegado",
        )
        cls.funcionario = make_employee(
            "funcionario", "11.111.113-3", cls.d1, cls.roles["ROL04"],
            first_name="Fabiola", last_name="Funciona",
        )
        cls.otro_funcionario = make_employee(
            "otro.funcionario", "11.111.114-4", cls.d1, cls.roles["ROL04"],
        )
        cls.tipo = AttentionType.objects.create(code="TAT01", name="Social")
        cls.sub = AttentionSubtype.objects.create(code="SAT001", name="Ayuda", attention_type=cls.tipo)
        cls.vecino = Neighbor.objects.create(
            identifier="11.111.111-1", full_name="María González", phone="+56911111111",
        )

    def _login(self, username):
        self.client.logout()
        assert self.client.login(username=username, password=DEMO_PASSWORD)

    def _flashed(self, resp):
        return " ".join(item["text"] for item in resp.context["sgr_messages"])

    def _post_data(self, **extra):
        data = {
            "neighbor_rut": "12.345.678-5",
            "neighbor_name": "Nora Paredes Soto",
            "neighbor_phone": "+56 9 8765 4321",
            "delegation": str(self.d1.pk),
            "attention_type": str(self.tipo.pk),
            "attention_subtype": str(self.sub.pk),
            "description": "Solicitud de apoyo social para la familia.",
        }
        data.update(extra)
        return data

    def _attention(self, responsible=None, delegation=None, **extra):
        extra.setdefault("description", "Atención de prueba del bloque 2B.")
        return Attention.objects.create(
            neighbor=self.vecino, delegation=delegation or self.d1,
            attention_type=self.tipo, attention_subtype=self.sub,
            responsible=(responsible or self.funcionario).user, **extra,
        )

    def _edit_data(self, **extra):
        data = {
            "attention_type": str(self.tipo.pk),
            "attention_subtype": str(self.sub.pk),
            "description": "Descripción editada de la atención.",
            "status": "in_progress",
            "unresolved_reason": "",
        }
        data.update(extra)
        return data


# ===========================================================================
# 2.5 Datos obligatorios del vecino y visita a terreno
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class NeighborDataTests(_Base):
    def test_rut_nombre_y_telefono_son_obligatorios(self):
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data(
            neighbor_rut="", neighbor_name="", neighbor_phone="",
        ))
        self.assertEqual(resp.status_code, 200)
        errors = resp.context["form"].errors
        for name in ("neighbor_rut", "neighbor_name", "neighbor_phone"):
            self.assertIn(name, errors)
        self.assertEqual(Attention.objects.count(), 0)

    def test_valida_rut_nombre_y_telefono(self):
        self._login("funcionario")
        cases = (
            ({"neighbor_rut": "12.345.678-9"}, "neighbor_rut", "dígito verificador"),
            ({"neighbor_rut": "abc"}, "neighbor_rut", "RUT válido"),
            ({"neighbor_name": "Nora"}, "neighbor_name", "nombre y apellido"),
            ({"neighbor_name": "Nora P4redes"}, "neighbor_name", "solo puede tener letras"),
            ({"neighbor_phone": "12345"}, "neighbor_phone", "9 dígitos"),
            ({"neighbor_phone": "fono"}, "neighbor_phone", "teléfono válido"),
        )
        for extra, field, message in cases:
            resp = self.client.post(reverse("attentions_new"), self._post_data(**extra))
            self.assertEqual(resp.status_code, 200, extra)
            self.assertIn(message, " ".join(resp.context["form"].errors[field]), extra)
        self.assertEqual(Attention.objects.count(), 0)

    def test_registra_vecino_nuevo_con_datos_normalizados(self):
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data(
            neighbor_rut="123456785", neighbor_name="  nora   paredes soto ",
            neighbor_phone="9 8765 4321",
        ))
        self.assertEqual(resp.status_code, 302)
        neighbor = Neighbor.objects.get(identifier="12.345.678-5")
        self.assertEqual(neighbor.full_name, "nora paredes soto")
        self.assertEqual(neighbor.phone, "+56987654321")
        self.assertEqual(Attention.objects.get().neighbor, neighbor)

    def test_reutiliza_vecino_por_rut_y_actualiza_contacto(self):
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data(
            neighbor_rut="11111111-1", neighbor_name="María González Rojas",
            neighbor_phone="+56 9 2222 3333",
        ))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Neighbor.objects.count(), 1)
        self.vecino.refresh_from_db()
        self.assertEqual(self.vecino.full_name, "María González Rojas")
        self.assertEqual(self.vecino.phone, "+56922223333")

    def test_vecino_eliminado_logicamente_se_reactiva(self):
        Neighbor.objects.filter(pk=self.vecino.pk).update(deleted_at=timezone.now())
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data(
            neighbor_rut="11.111.111-1", neighbor_name="María González",
        ))
        self.assertEqual(resp.status_code, 302)
        self.vecino.refresh_from_db()
        self.assertIsNone(self.vecino.deleted_at)
        self.assertEqual(Neighbor.objects.count(), 1)

    def test_requiere_visita(self):
        self._login("funcionario")
        self.client.post(reverse("attentions_new"), self._post_data(requires_visit="on"))
        self.client.post(reverse("attentions_new"), self._post_data(
            description="Otra solicitud sin visita a terreno.",
        ))
        flags = list(Attention.objects.order_by("pk").values_list("requires_visit", flat=True))
        self.assertEqual(flags, [True, False])
        # Filtro del listado y columna del Excel.
        resp = self.client.get(reverse("attentions"), {"visita": "si"})
        self.assertEqual(len(resp.context["rows"]), 1)
        sheet = load_workbook(io.BytesIO(
            self.client.get(reverse("attentions_export"), {"orden": "numero"}).content
        )).active
        headers = [cell.value for cell in sheet[1]]
        column = headers.index("Requiere visita")
        self.assertEqual([row[column].value for row in sheet.iter_rows(min_row=2)], ["Sí", "No"])

    def test_editar_puede_marcar_la_visita_y_no_cambia_el_vecino(self):
        attention = self._attention(responsible=self.delegado)
        self._login("delegado")
        resp = self.client.post(
            reverse("attentions_edit", args=[attention.pk]),
            self._edit_data(requires_visit="on", neighbor_rut="12.345.678-5"),
        )
        self.assertEqual(resp.status_code, 302)
        attention.refresh_from_db()
        self.assertTrue(attention.requires_visit)
        self.assertEqual(attention.neighbor, self.vecino)

    def test_buscador_devuelve_datos_y_encuentra_por_rut_sin_puntos(self):
        self._login("funcionario")
        for query in ("11111111", "11.111.111-1", "maria gonzalez", "MARÍA"):
            resp = self.client.get(reverse("attention_neighbors"), {"q": query})
            results = resp.json()["results"]
            self.assertEqual(len(results), 1, query)
            self.assertEqual(results[0]["rut"], "11.111.111-1")
            self.assertEqual(results[0]["name"], "María González")
            self.assertEqual(results[0]["phone"], "+56911111111")

    def test_formulario_de_ingreso_muestra_los_campos(self):
        self._login("funcionario")
        resp = self.client.get(reverse("attentions_new"))
        for name in ("neighbor_rut", "neighbor_name", "neighbor_phone", "requires_visit"):
            self.assertContains(resp, f'name="{name}"')
        self.assertNotContains(resp, 'name="neighbor"')
        self.assertContains(resp, "Hoy llevas 0 de 7 atenciones ingresadas")


# ===========================================================================
# 2.6 Estado "Sin resolver" y hasta 3 gestiones
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class UnresolvedStatusTests(_Base):
    def test_sin_resolver_exige_motivo(self):
        attention = self._attention(responsible=self.delegado)
        self._login("delegado")
        url = reverse("attentions_edit", args=[attention.pk])
        resp = self.client.post(url, self._edit_data(status="unresolved", unresolved_reason="corto"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("unresolved_reason", resp.context["form"].errors)
        attention.refresh_from_db()
        self.assertEqual(attention.status, "received")

        resp = self.client.post(url, self._edit_data(
            status="unresolved", unresolved_reason="El vecino no respondió en tres contactos.",
        ))
        self.assertEqual(resp.status_code, 302)
        attention.refresh_from_db()
        self.assertEqual(attention.status, "unresolved")
        self.assertEqual(attention.status_display, "Sin resolver")
        self.assertEqual(attention.unresolved_reason, "El vecino no respondió en tres contactos.")

    def test_reabrir_limpia_el_motivo(self):
        attention = self._attention(
            responsible=self.delegado, status="unresolved",
            unresolved_reason="Motivo anterior de la baja.",
        )
        self._login("delegado")
        self.client.post(reverse("attentions_edit", args=[attention.pk]), self._edit_data(
            status="in_progress", unresolved_reason="Motivo anterior de la baja.",
        ))
        attention.refresh_from_db()
        self.assertEqual(attention.status, "in_progress")
        self.assertEqual(attention.unresolved_reason, "")

    def test_listado_filtra_y_muestra_sin_resolver(self):
        self._attention(status="unresolved", unresolved_reason="Sin datos de contacto válidos.")
        self._attention()
        self._login("superadmin")
        resp = self.client.get(reverse("attentions"), {"estado": "unresolved"})
        self.assertEqual(len(resp.context["rows"]), 1)
        self.assertContains(resp, '<span class="badge b-bad">Sin resolver</span>', html=True)
        self.assertIn(("unresolved", "Sin resolver"), resp.context["status_options"])

    def test_orden_por_estado_deja_sin_resolver_al_final(self):
        a_unresolved = self._attention(status="unresolved", unresolved_reason="Caso dado de baja.")
        self._attention(status="resolved")
        self._attention()
        self._login("superadmin")
        numbers = [row["cells"][0]["text"] for row in
                   self.client.get(reverse("attentions"), {"orden": "estado"}).context["rows"]]
        self.assertEqual(numbers[-1], a_unresolved.number)


@override_settings(STORAGES=TEST_STORAGES)
class FollowUpTests(_Base):
    def _add(self, attention, text="Llamada al vecino para coordinar."):
        return self.client.post(
            reverse("attention_follow_up_new", args=[attention.pk]), {"description": text},
        )

    def test_hasta_3_gestiones(self):
        attention = self._attention()
        self._login("funcionario")
        for expected in (1, 2, 3):
            resp = self._add(attention, f"Gestión número {expected} realizada con el vecino.")
            self.assertRedirects(resp, reverse("attentions_detail", args=[attention.pk]))
        self.assertEqual(
            list(attention.follow_ups.values_list("sequence", flat=True)), [1, 2, 3],
        )
        resp = self._add(attention)
        self.assertEqual(attention.follow_ups.count(), 3)
        follow = self.client.get(reverse("attentions_detail", args=[attention.pk]))
        self.assertIn("ya tiene las 3 gestiones", self._flashed(follow))
        self.assertContains(follow, "3 de 3")
        self.assertNotContains(follow, 'id="followUpForm"')

    def test_la_base_de_datos_impide_una_cuarta(self):
        attention = self._attention()
        for sequence in (1, 2, 3):
            AttentionFollowUp.objects.create(
                attention=attention, sequence=sequence, description="Gestión registrada.",
                performed_by=self.funcionario.user,
            )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttentionFollowUp.objects.create(
                    attention=attention, sequence=4, description="Cuarta gestión.",
                    performed_by=self.funcionario.user,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttentionFollowUp.objects.create(
                    attention=attention, sequence=2, description="Repetida.",
                    performed_by=self.funcionario.user,
                )

    def test_las_gestiones_no_puntuan_como_atencion_nueva(self):
        attention = self._attention()
        self._login("funcionario")
        self._add(attention)
        self._add(attention, "Segunda gestión realizada con el vecino.")
        self.assertEqual(Attention.objects.count(), 1)
        self.assertEqual(rules.attentions_entered_on(self.funcionario.user).count(), 1)
        self.assertEqual(rules.scoring_attentions().count(), 1)

    def test_gestion_valida_texto_y_estado_abierto(self):
        attention = self._attention(status="resolved")
        self._login("funcionario")
        self._add(attention)
        self.assertEqual(attention.follow_ups.count(), 0)
        open_attention = self._attention()
        resp = self._add(open_attention, "corto")
        self.assertEqual(open_attention.follow_ups.count(), 0)
        follow = self.client.get(resp["Location"])
        self.assertIn("al menos 10 caracteres", self._flashed(follow))

    def test_alcance_y_metodo(self):
        ajena = self._attention(responsible=self.otro_funcionario)
        self._login("funcionario")
        self.assertEqual(self._add(ajena).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("attention_follow_up_new", args=[ajena.pk])).status_code, 404,
        )
        self.assertEqual(ajena.follow_ups.count(), 0)

    def test_consulta_muestra_las_gestiones(self):
        attention = self._attention()
        AttentionFollowUp.objects.create(
            attention=attention, sequence=1, description="Visita al domicilio realizada.",
            performed_by=self.funcionario.user,
        )
        self._login("funcionario")
        resp = self.client.get(reverse("attentions_detail", args=[attention.pk]))
        self.assertContains(resp, "Gestiones de seguimiento")
        self.assertContains(resp, "Visita al domicilio realizada.")
        self.assertContains(resp, "1 de 3")
        self.assertContains(resp, "Nueva gestión (2 de 3)")
        self.assertContains(resp, "no suma al puntaje operativo")


# ===========================================================================
# 2.7 Tope diario, cierre semanal y puntaje operativo
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class DailyLimitTests(_Base):
    def test_maximo_7_ingresos_por_dia(self):
        for _ in range(7):
            self._attention()
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "máximo de 7 atenciones ingresadas hoy")
        self.assertEqual(Attention.objects.count(), 7)

    def test_los_ingresos_de_otros_dias_no_cuentan(self):
        for _ in range(7):
            old = self._attention()
            Attention.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data())
        self.assertEqual(resp.status_code, 302)

    def test_el_tope_es_por_funcionario(self):
        for _ in range(7):
            self._attention(responsible=self.otro_funcionario)
        self._login("funcionario")
        self.assertEqual(self.client.post(reverse("attentions_new"), self._post_data()).status_code, 302)

    def test_superadministrador_no_tiene_tope(self):
        for _ in range(7):
            Attention.objects.create(
                neighbor=self.vecino, delegation=self.d1, attention_type=self.tipo,
                attention_subtype=self.sub, description="Ingreso del superadministrador.",
                responsible=self.superadmin,
            )
        self._login("superadmin")
        self.assertEqual(self.client.post(reverse("attentions_new"), self._post_data()).status_code, 302)

    @override_settings(ATTENTION_DAILY_LIMIT=2)
    def test_tope_configurable(self):
        self._attention()
        self._attention()
        self._login("funcionario")
        resp = self.client.post(reverse("attentions_new"), self._post_data())
        self.assertContains(resp, "máximo de 2 atenciones")


@override_settings(STORAGES=TEST_STORAGES)
class WeeklyClosureTests(_Base):
    def _this_week(self):
        return rules.week_start(rules.local_day())

    def _close(self, delegation, start=None, username="coordinador"):
        self._login(username)
        return self.client.post(reverse("attention_week_closures"), {
            "accion": "cerrar", "delegacion": delegation.pk,
            "semana": (start or self._this_week()).isoformat(),
        })

    def test_cerrar_bloquea_ingreso_en_esa_delegacion(self):
        self._close(self.d1)
        self.assertTrue(WeeklyClosure.alive.filter(delegation=self.d1, week_start=self._this_week()).exists())
        resp = self.client.post(reverse("attentions_new"), self._post_data())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "está cerrada para DEL01")
        # Otra delegación sigue abierta.
        resp = self.client.post(reverse("attentions_new"), self._post_data(delegation=str(self.d2.pk)))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Attention.objects.count(), 1)

    def test_cerrar_bloquea_la_edicion_y_reabrir_la_habilita(self):
        attention = self._attention(responsible=self.delegado)
        self._close(self.d1)
        self._login("delegado")
        edit_url = reverse("attentions_edit", args=[attention.pk])
        resp = self.client.get(edit_url)
        self.assertRedirects(resp, reverse("attentions_detail", args=[attention.pk]))
        resp = self.client.post(edit_url, self._edit_data(description="Intento de cambio en semana cerrada."))
        self.assertEqual(resp.status_code, 302)
        attention.refresh_from_db()
        self.assertEqual(attention.description, "Atención de prueba del bloque 2B.")
        detail = self.client.get(reverse("attentions_detail", args=[attention.pk]))
        self.assertContains(detail, "Semana cerrada")
        listing = self.client.get(reverse("attentions"))
        self.assertTrue(listing.context["rows"][0]["locked"])
        self.assertContains(listing, 'data-tip="Semana cerrada"')

        closure = WeeklyClosure.alive.get(delegation=self.d1)
        self._login("coordinador")
        self.client.post(reverse("attention_week_closures"), {"accion": "reabrir", "cierre": closure.pk})
        self.assertFalse(WeeklyClosure.alive.filter(pk=closure.pk).exists())
        self._login("delegado")
        self.assertEqual(self.client.get(edit_url).status_code, 200)

    def test_semana_cerrada_de_otra_fecha_no_bloquea_la_actual(self):
        last_week = self._this_week() - timedelta(days=7)
        old = self._attention(responsible=self.delegado)
        Attention.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=7))
        recent = self._attention(responsible=self.delegado)
        self._close(self.d1, start=last_week)
        self._login("delegado")
        self.assertEqual(self.client.get(reverse("attentions_edit", args=[old.pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse("attentions_edit", args=[recent.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("attentions_new"), self._post_data()).status_code, 302)

    def test_gestiones_siguen_permitidas_si_la_semana_actual_esta_abierta(self):
        last_week = self._this_week() - timedelta(days=7)
        old = self._attention()
        Attention.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=7))
        self._close(self.d1, start=last_week)
        self._login("funcionario")
        self.client.post(reverse("attention_follow_up_new", args=[old.pk]),
                         {"description": "Seguimiento de un caso de la semana pasada."})
        self.assertEqual(old.follow_ups.count(), 1)
        # Con la semana actual cerrada ya no se registran gestiones.
        self._close(self.d1)
        self._login("funcionario")
        self.client.post(reverse("attention_follow_up_new", args=[old.pk]),
                         {"description": "Otra gestión con la semana actual cerrada."})
        self.assertEqual(old.follow_ups.count(), 1)

    def test_delegado_cierra_su_delegacion_pero_no_reabre(self):
        resp = self._close(self.d1, username="delegado")
        self.assertEqual(resp.status_code, 302)
        closure = WeeklyClosure.alive.get(delegation=self.d1)
        # No puede cerrar una delegación que no es la suya.
        self._close(self.d2, username="delegado")
        self.assertFalse(WeeklyClosure.objects.filter(delegation=self.d2).exists())
        resp = self.client.post(reverse("attention_week_closures"), {"accion": "reabrir", "cierre": closure.pk})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(WeeklyClosure.alive.filter(pk=closure.pk).exists())
        page = self.client.get(reverse("attention_week_closures"))
        self.assertFalse(page.context["can_reopen"])

    def test_funcionario_no_accede_al_cierre(self):
        self._login("funcionario")
        self.assertEqual(self.client.get(reverse("attention_week_closures")).status_code, 403)
        resp = self.client.post(reverse("attention_week_closures"), {
            "accion": "cerrar", "delegacion": self.d1.pk, "semana": self._this_week().isoformat(),
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(WeeklyClosure.objects.exists())
        self.assertNotContains(self.client.get(reverse("attentions")), "Cierre semanal")

    def test_semana_invalida_y_cierre_repetido(self):
        self._close(self.d1, start=self._this_week() + timedelta(days=7))   # futura
        self._close(self.d1, start=self._this_week() + timedelta(days=1))   # no es lunes
        self._close(self.d1, start=self._this_week() - timedelta(days=7 * 20))  # muy antigua
        self.assertFalse(WeeklyClosure.objects.exists())
        self._close(self.d1)
        resp = self._close(self.d1)
        self.assertIn("ya estaba cerrada", self._flashed(self.client.get(resp["Location"])))
        self.assertEqual(WeeklyClosure.objects.count(), 1)

    def test_volver_a_cerrar_reutiliza_el_registro_y_queda_auditado(self):
        self._close(self.d1)
        closure = WeeklyClosure.alive.get()
        self.client.post(reverse("attention_week_closures"), {"accion": "reabrir", "cierre": closure.pk})
        self._close(self.d1)
        self.assertEqual(WeeklyClosure.objects.count(), 1)
        self.assertEqual(WeeklyClosure.alive.count(), 1)
        actions = list(AuditLog.objects.filter(module="attentions").values_list("action", flat=True))
        self.assertEqual(actions.count("close_week"), 2)
        self.assertEqual(actions.count("reopen_week"), 1)

    def test_pantalla_resume_atenciones_y_puntaje(self):
        self._attention(counts_for_score=True)
        self._attention(responsible=self.delegado, counts_for_score=False)
        self._close(self.d1)
        page = self.client.get(reverse("attention_week_closures"))
        row = page.context["rows"][0]
        self.assertEqual((row["total"], row["puntaje"]), (2, 1))
        self.assertContains(page, "Semanas cerradas")


@override_settings(STORAGES=TEST_STORAGES)
class ScoreTests(_Base):
    def test_ingresos_del_delegado_no_puntuan(self):
        for username in ("delegado", "funcionario", "coordinador"):
            self._login(username)
            resp = self.client.post(reverse("attentions_new"), self._post_data(
                description=f"Atención ingresada por {username} para la prueba.",
            ))
            self.assertEqual(resp.status_code, 302, username)
        flags = dict(
            Attention.objects.values_list("responsible__username", "counts_for_score")
        )
        self.assertEqual(flags, {"delegado": False, "funcionario": True, "coordinador": True})
        self.assertEqual(rules.scoring_attentions().count(), 2)

    def test_consulta_y_excel_muestran_el_puntaje(self):
        attention = self._attention(responsible=self.delegado, counts_for_score=False)
        self._login("delegado")
        resp = self.client.get(reverse("attentions_detail", args=[attention.pk]))
        self.assertContains(resp, "Puntaje operativo: No cuenta (ingreso del rol Delegado)")
        sheet = load_workbook(io.BytesIO(self.client.get(reverse("attentions_export")).content)).active
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(sheet.cell(row=2, column=headers.index("Puntaje operativo") + 1).value,
                         "No cuenta (ingreso del rol Delegado)")

    def test_migracion_marca_ingresos_previos_del_delegado(self):
        migration = importlib.import_module("operaciones.migrations.0017_atenciones_ampliadas")
        del_attention = self._attention(responsible=self.delegado)
        fun_attention = self._attention()
        self.assertTrue(del_attention.counts_for_score)
        migration.mark_delegate_entries(django_apps, None)
        del_attention.refresh_from_db()
        fun_attention.refresh_from_db()
        self.assertFalse(del_attention.counts_for_score)
        self.assertTrue(fun_attention.counts_for_score)
