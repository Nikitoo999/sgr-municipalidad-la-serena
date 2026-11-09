"""Pruebas del Bloque 2A: mantenedores, códigos automáticos, filtros y archivos.

Cubre:
- 2.1 Código correlativo automático (DEL01, ROL01, ITM001, TAT01, SAT001):
  generado en ``save()``, sin input al crear, solo lectura al editar, con
  reintento si dos guardados chocan, y la migración que rellena ITM/SAT.
- 2.2 Títulos, botones, mensajes y modal de borrado con el nombre propio.
- 2.3 Estado del listado en la sesión (último filtro, orden, filas por página
  y página) con ``?limpiar=1``; orden por columna y filtros propios en los
  mantenedores; búsqueda resuelta en la BD (también en SQLite).
- 2.4 Excel ``<modulo>_<AAAAMMDD_HHMM>_<usuario>.xlsx`` y archivos guardados
  con el código del registro como prefijo.
"""

import html
import importlib
import re
import shutil
import tempfile
from datetime import date
from io import BytesIO
from unittest import mock

from django.apps import apps as django_apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.db.models import QuerySet
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from operaciones.models import (
    Activity,
    Attention,
    Evidence,
    Neighbor,
    Task,
    attention_image_path,
)
from portal.crud.search import apply_search
from portal.crud.views import LIST_STATE_SESSION_KEY, export_filename
from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
    make_user,
)
from sgr_core.models import (
    AttentionSubtype,
    AttentionType,
    Delegation,
    InstitutionalGoal,
    Period,
    ProjectItem,
    Role,
)

MEDIA_TMP = tempfile.mkdtemp(prefix="sgr_media_2a_")


def png_file(name="evidencia.png"):
    buffer = BytesIO()
    Image.new("RGB", (12, 12), (146, 0, 0)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class _Base(TestCase):
    """Datos comunes: 4 roles base, 3 delegaciones y un usuario por rol."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828", address="Calle 1")
        cls.d2 = make_delegation("Avenida del Mar", "DEL02", commune="Coquimbo")
        cls.d3 = make_delegation("Sector Cerrado", "DEL03", status="Inactiva")
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
        cls.funcionario_mar = make_employee(
            "funcionario.mar", "11.111.114-4", cls.d2, cls.roles["ROL04"],
            first_name="Mario", last_name="Mar",
        )

    def _login(self, username):
        self.client.logout()
        assert self.client.login(username=username, password=DEMO_PASSWORD)

    def _first_column(self, resp):
        return [row["cells"][0]["text"] for row in resp.context["rows"]]

    def _flashed(self, resp):
        return " ".join(item["text"] for item in resp.context["sgr_messages"])


# ===========================================================================
# 2.1 Código automático y correlativo
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class AutoCodeModelTests(_Base):
    def test_formatos_por_modelo(self):
        self.assertEqual(Delegation.next_code(), "DEL04")
        self.assertEqual(Role.next_code(), "ROL05")
        self.assertEqual(ProjectItem.next_code(), "ITM001")
        self.assertEqual(AttentionType.next_code(), "TAT01")
        tipo = AttentionType.objects.create(name="Social")
        self.assertEqual(tipo.code, "TAT01")
        sub = AttentionSubtype.objects.create(name="Ayuda", attention_type=tipo)
        self.assertEqual(sub.code, "SAT001")

    def test_correlativo_sigue_al_mayor_e_ignora_formatos_ajenos(self):
        Delegation.objects.create(name="Con hueco", code="DEL09")
        Delegation.objects.create(name="Otro formato", code="PAG50")
        nueva = Delegation.objects.create(name="Nueva")
        self.assertEqual(nueva.code, "DEL10")

    def test_cuenta_los_eliminados_logicamente(self):
        # El código es único en toda la tabla: un eliminado no se reutiliza.
        self.d3.deleted_at = timezone.now()
        self.d3.save(update_fields=["deleted_at"])
        self.assertEqual(Delegation.objects.create(name="Otra").code, "DEL04")

    def test_codigo_informado_se_respeta(self):
        item = ProjectItem.objects.create(code="ITM050", name="Manual")
        self.assertEqual(item.code, "ITM050")
        self.assertEqual(ProjectItem.objects.create(name="Siguiente").code, "ITM051")

    def test_editar_no_cambia_el_codigo(self):
        item = ProjectItem.objects.create(name="Uno")
        codigo = item.code
        item.name = "Uno editado"
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.code, codigo)

    def test_reintenta_si_dos_guardados_chocan(self):
        # Simula la carrera: la primera vez next_code entrega un código que
        # otra persona acaba de guardar; el INSERT falla y se reintenta.
        ProjectItem.objects.create(code="ITM001", name="Ganó la carrera")
        real_next = ProjectItem.next_code.__func__
        calls = []

        def flaky_next(cls):
            calls.append(1)
            return "ITM001" if len(calls) == 1 else real_next(cls)

        with mock.patch.object(ProjectItem, "next_code", classmethod(flaky_next)):
            item = ProjectItem.objects.create(name="Perdió y reintentó")
        self.assertEqual(item.code, "ITM002")
        self.assertEqual(len(calls), 2)

    def test_otro_integrity_error_no_se_oculta(self):
        with mock.patch.object(ProjectItem, "next_code", classmethod(lambda cls: "ITM777")):
            with mock.patch(
                "django.db.models.Model.save", side_effect=IntegrityError("otra regla"),
            ):
                with self.assertRaises(IntegrityError):
                    ProjectItem(name="Falla por otra razón").save()

    def test_migracion_rellena_codigos_de_dos_digitos(self):
        migration = importlib.import_module("sgr_core.migrations.0011_codigos_correlativos")
        tipo = AttentionType.objects.create(code="TAT01", name="Social")
        ProjectItem.objects.create(code="ITM01", name="Uno")
        ProjectItem.objects.create(code="ITM02", name="Dos")
        ProjectItem.objects.create(code="ITM002", name="Choque")  # ocupa el destino de ITM02
        ProjectItem.objects.create(code="OTRO1", name="Fuera de formato")
        AttentionSubtype.objects.create(code="SAT07", name="Sub", attention_type=tipo)

        migration.pad_codes(django_apps, None)

        codes = set(ProjectItem.objects.values_list("code", flat=True))
        self.assertEqual(codes, {"ITM001", "ITM02", "ITM002", "OTRO1"})
        self.assertTrue(AttentionSubtype.objects.filter(code="SAT007").exists())
        # Los tipos usan 2 dígitos: no se tocan.
        self.assertTrue(AttentionType.objects.filter(code="TAT01").exists())


@override_settings(STORAGES=TEST_STORAGES)
class AutoCodeFormTests(_Base):
    def test_crear_no_tiene_input_de_codigo_y_muestra_el_proximo(self):
        self._login("superadmin")
        for url_name, expected in (
            ("delegations_new", "DEL04"), ("roles_new", "ROL05"),
            ("items_new", "ITM001"), ("attention_types_new", "TAT01"),
        ):
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, url_name)
            self.assertNotIn("code", resp.context["form"].fields, url_name)
            self.assertEqual(resp.context["code_preview"], expected, url_name)
            self.assertNotContains(resp, 'name="code"')
            self.assertContains(resp, "Se asigna automáticamente al guardar")

    def test_editar_muestra_el_codigo_deshabilitado(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations_edit", args=[self.d1.pk]))
        field = resp.context["form"].fields["code"]
        self.assertTrue(field.disabled)
        self.assertRegex(
            resp.content.decode(), r'<input[^>]*name="code"[^>]*value="DEL01"[^>]*disabled',
        )

    def test_crear_desde_el_mantenedor_asigna_codigo_y_lo_informa(self):
        self._login("superadmin")
        resp = self.client.post(reverse("items_new"), {
            "name": "Operativos", "description": "", "status": "Activo",
        }, follow=True)
        item = ProjectItem.alive.get(name="Operativos")
        self.assertEqual(item.code, "ITM001")
        self.assertIn("Ítem creado correctamente con el código ITM001.", self._flashed(resp))

    def test_sub_atencion_desde_el_mantenedor(self):
        tipo = AttentionType.objects.create(name="Territorial")
        self._login("coordinador")
        resp = self.client.post(reverse("attention_subtypes_new"), {
            "name": "Luminarias", "attention_type": str(tipo.pk), "status": "Activo",
        }, follow=True)
        self.assertEqual(AttentionSubtype.alive.get(name="Luminarias").code, "SAT001")
        self.assertIn("Sub atención creada correctamente", self._flashed(resp))


# ===========================================================================
# 2.2 Títulos y modales con nombre propio
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class ProperTitlesTests(_Base):
    def test_titulos_de_crear_editar_y_consultar(self):
        self._login("superadmin")
        item = ProjectItem.objects.create(name="Ítem demo")
        tipo = AttentionType.objects.create(name="Social")
        sub = AttentionSubtype.objects.create(name="Ayuda", attention_type=tipo)
        cases = (
            (reverse("delegations_new"), "Nueva delegación"),
            (reverse("users_new"), "Nuevo usuario"),
            (reverse("roles_new"), "Nuevo rol"),
            (reverse("items_new"), "Nuevo ítem"),
            (reverse("attention_types_new"), "Nuevo tipo de atención"),
            (reverse("attention_subtypes_new"), "Nueva sub atención"),
            (reverse("delegations_edit", args=[self.d1.pk]), "Editar delegación"),
            (reverse("users_edit", args=[self.funcionario.pk]), "Editar usuario"),
            (reverse("items_edit", args=[item.pk]), "Editar ítem"),
            (reverse("attention_subtypes_detail", args=[sub.pk]), "Consulta de sub atención"),
            (reverse("users_detail", args=[self.funcionario.pk]), "Consulta de usuario"),
        )
        for url, title in cases:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            self.assertContains(resp, f"<h1>{title}</h1>", html=False)
            self.assertNotContains(resp, "Crear registro")
            self.assertNotContains(resp, "Editar registro")

    def test_boton_de_guardar_con_nombre_propio(self):
        self._login("superadmin")
        self.assertContains(self.client.get(reverse("delegations_new")), "Guardar delegación")
        self.assertContains(
            self.client.get(reverse("delegations_edit", args=[self.d1.pk])), "Guardar cambios",
        )

    def test_listado_con_boton_propio_y_modal_de_borrado_con_el_registro(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations"))
        content = html.unescape(resp.content.decode())
        self.assertIn("Nueva delegación", content)
        self.assertNotIn("Nuevo registro", content)
        self.assertIn('data-delete-title="¿Eliminar la delegación «DEL01 · Centro»?"', content)
        self.assertIn("La delegación se marcará como eliminada", content)

        resp = self.client.get(reverse("users"))
        content = html.unescape(resp.content.decode())
        self.assertIn("Nuevo usuario", content)
        self.assertIn("¿Eliminar el usuario «Fabiola Funciona»?", content)
        self.assertIn("El usuario se marcará como eliminado", content)

    def test_mensajes_con_genero_correcto(self):
        self._login("superadmin")
        resp = self.client.post(reverse("items_delete", args=[
            ProjectItem.objects.create(name="Borrable").pk,
        ]), follow=True)
        self.assertIn("Ítem eliminado correctamente.", self._flashed(resp))
        resp = self.client.post(reverse("delegations_edit", args=[self.d2.pk]), {
            "name": "Avenida del Mar", "commune": "Coquimbo", "address": "",
            "color": "", "status": "Activa",
        }, follow=True)
        self.assertIn("Delegación actualizada correctamente.", self._flashed(resp))


# ===========================================================================
# 2.3 Estado del listado en la sesión, orden por columna y filtros propios
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class SessionStateTests(_Base):
    def test_ultimo_filtro_persiste_al_volver_y_refrescar(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations"), {"estado": "Inactiva"})
        self.assertEqual(self._first_column(resp), ["DEL03"])
        # Volver al listado sin parámetros (menú, F5, después de guardar).
        resp = self.client.get(reverse("delegations"))
        self.assertEqual(self._first_column(resp), ["DEL03"])
        self.assertEqual(resp.context["estado"], "Inactiva")
        self.assertEqual(
            self.client.session[LIST_STATE_SESSION_KEY]["delegations"], {"estado": "Inactiva"},
        )

    def test_limpiar_borra_el_estado_guardado(self):
        self._login("superadmin")
        self.client.get(reverse("delegations"), {"estado": "Inactiva", "por_pagina": 15})
        resp = self.client.get(reverse("delegations"), {"limpiar": 1})
        self.assertRedirects(resp, reverse("delegations"))
        resp = self.client.get(reverse("delegations"))
        self.assertEqual(self._first_column(resp), ["DEL01", "DEL02", "DEL03"])
        self.assertEqual(resp.context["page_size"], 5)
        self.assertNotIn("delegations", self.client.session.get(LIST_STATE_SESSION_KEY, {}))

    def test_boton_limpiar_apunta_a_limpiar(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations"))
        self.assertContains(resp, 'href="/delegaciones/?limpiar=1"')

    def test_cada_tabla_recuerda_lo_suyo(self):
        self._login("superadmin")
        ProjectItem.objects.create(name="Activo")
        ProjectItem.objects.create(name="Inactivo", status="Inactivo")
        self.client.get(reverse("items"), {"estado": "Inactivo"})
        self.client.get(reverse("delegations"), {"q": "centro"})
        self.assertEqual(self._first_column(self.client.get(reverse("delegations"))), ["DEL01"])
        items = self.client.get(reverse("items"))
        self.assertEqual([row["cells"][1]["text"] for row in items.context["rows"]], ["Inactivo"])

    def test_borrar_la_busqueda_reemplaza_lo_guardado(self):
        self._login("superadmin")
        self.client.get(reverse("delegations"), {"q": "centro"})
        # El formulario envía q vacío: eso manda (no se restaura "centro").
        resp = self.client.get(reverse("delegations"), {"q": "", "estado": ""})
        self.assertEqual(len(resp.context["rows"]), 3)
        self.assertEqual(len(self.client.get(reverse("delegations")).context["rows"]), 3)

    def test_filas_por_pagina_5_15_30_y_se_recuerdan(self):
        for i in range(4, 40):
            Delegation.objects.create(name=f"Extra {i}")
        self._login("superadmin")
        for size in (5, 15, 30):
            resp = self.client.get(reverse("delegations"), {"por_pagina": size})
            self.assertEqual(len(resp.context["rows"]), size)
        self.assertEqual(resp.context["page_size_options"], (5, 15, 30))
        # Se recuerda el último tamaño (y la página) al volver.
        self.client.get(reverse("delegations"), {"por_pagina": 15, "page": 2})
        resp = self.client.get(reverse("delegations"))
        self.assertEqual(resp.context["page_size"], 15)
        self.assertContains(resp, "Mostrando 16 a 30 de 39 registros")

    def test_por_pagina_invalido_usa_5(self):
        self._login("superadmin")
        for bad in ("7", "0", "abc", "-5", "1000"):
            resp = self.client.get(reverse("delegations"), {"por_pagina": bad})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context["page_size"], 5, bad)

    def test_exportar_usa_los_filtros_recordados(self):
        self._login("superadmin")
        self.client.get(reverse("delegations"), {"estado": "Inactiva", "orden": "-nombre"})
        resp = self.client.get(reverse("delegations"))
        self.assertIn("estado=Inactiva", resp.context["export_url"])
        self.assertIn("orden=-nombre", resp.context["export_url"])
        self.assertNotIn("por_pagina", resp.context["export_url"])

    def test_atenciones_tambien_recuerdan_filtros(self):
        tipo = AttentionType.objects.create(name="Social")
        sub = AttentionSubtype.objects.create(name="Ayuda", attention_type=tipo)
        vecino = Neighbor.objects.create(identifier="22.222.222-2", full_name="Pedro Soto")
        for status in ("received", "resolved"):
            Attention.objects.create(
                neighbor=vecino, delegation=self.d1, attention_type=tipo,
                attention_subtype=sub, description="Descripción de prueba.",
                responsible=self.funcionario.user, status=status,
            )
        self._login("superadmin")
        self.client.get(reverse("attentions"), {"estado": "resolved", "por_pagina": 10})
        resp = self.client.get(reverse("attentions"))
        self.assertEqual(len(resp.context["rows"]), 1)
        self.assertEqual(resp.context["page_size"], 10)
        self.assertContains(resp, 'href="/atenciones/?limpiar=1"')
        self.client.get(reverse("attentions"), {"limpiar": 1})
        self.assertEqual(len(self.client.get(reverse("attentions")).context["rows"]), 2)


@override_settings(STORAGES=TEST_STORAGES)
class SortAndFilterTests(_Base):
    def test_orden_por_columna_en_delegaciones(self):
        self._login("superadmin")
        self.assertEqual(
            self._first_column(self.client.get(reverse("delegations"), {"orden": "-codigo"})),
            ["DEL03", "DEL02", "DEL01"],
        )
        names = [row["cells"][1]["text"] for row in
                 self.client.get(reverse("delegations"), {"orden": "nombre"}).context["rows"]]
        self.assertEqual(names, ["Avenida del Mar", "Centro", "Sector Cerrado"])

    def test_orden_invalido_usa_el_orden_por_defecto(self):
        self._login("superadmin")
        for bad in ("zzz", "--codigo", "code", "codigo;DROP TABLE delegacion", " "):
            resp = self.client.get(reverse("delegations"), {"orden": bad})
            self.assertEqual(resp.status_code, 200, bad)
            self.assertEqual(self._first_column(resp), ["DEL01", "DEL02", "DEL03"], bad)

    def test_encabezados_ordenables_alternan_y_tienen_aria_sort(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations"), {"orden": "nombre"})
        header = next(h for h in resp.context["headers"] if h["label"] == "Nombre")
        self.assertEqual(header["aria_sort"], "ascending")
        self.assertIn("orden=-nombre", header["url"])
        self.assertContains(resp, 'aria-sort="ascending"')
        self.assertContains(resp, 'class="sortlink is-current"')
        # Cambiar el orden vuelve a la página 1.
        self.assertNotIn("page=", header["url"])

    def test_orden_se_conserva_al_filtrar(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations"), {"orden": "-nombre"})
        self.assertRegex(resp.content.decode(), r'<input type="hidden" name="orden" value="-nombre">')

    def test_roles_ordenados_por_modulos_y_filtrados_por_alcance(self):
        self._login("superadmin")
        resp = self.client.get(reverse("roles"), {"orden": "-modulos"})
        self.assertEqual(self._first_column(resp)[0], "ROL01")   # 11 módulos
        resp = self.client.get(reverse("roles"), {"alcance": "own_records"})
        self.assertEqual(self._first_column(resp), ["ROL04"])
        # Un alcance inventado se ignora.
        resp = self.client.get(reverse("roles"), {"alcance": "superpoderes"})
        self.assertEqual(len(resp.context["rows"]), 4)

    def test_usuarios_filtro_por_rol_delegacion_y_estado(self):
        self._login("superadmin")
        resp = self.client.get(reverse("users"), {"rol": self.roles["ROL04"].pk})
        self.assertEqual(sorted(self._first_column(resp)), ["11.111.113-3", "11.111.114-4"])
        # Delegación: base o autorizada (el coordinador tiene DEL02 autorizada).
        resp = self.client.get(reverse("users"), {"delegacion": self.d2.pk})
        self.assertEqual(sorted(self._first_column(resp)), ["11.111.111-1", "11.111.114-4"])
        self.funcionario.user.is_active = False
        self.funcionario.user.save(update_fields=["is_active"])
        resp = self.client.get(reverse("users"), {"estado": "Inactivo"})
        self.assertEqual(self._first_column(resp), ["11.111.113-3"])
        resp = self.client.get(reverse("users"), {"estado": "Activo", "orden": "rut"})
        self.assertNotIn("11.111.113-3", self._first_column(resp))

    def test_usuarios_las_opciones_respetan_el_alcance(self):
        # El delegado solo ve funcionarios de su delegación: el filtro de rol
        # no ofrece roles que no puede ver y un pk manipulado se ignora.
        self._login("delegado")
        resp = self.client.get(reverse("users"))
        rol = next(c for c in resp.context["filter_controls"] if c["param"] == "rol")
        self.assertEqual([o["label"] for o in rol["options"]], ["ROL04 · Funcionario"])
        deleg = next(c for c in resp.context["filter_controls"] if c["param"] == "delegacion")
        self.assertEqual([o["label"] for o in deleg["options"]], ["DEL01 · Centro"])
        resp = self.client.get(reverse("users"), {"delegacion": self.d2.pk})
        self.assertEqual(self._first_column(resp), ["11.111.113-3"])

    def test_sub_atenciones_filtro_por_tipo(self):
        social = AttentionType.objects.create(name="Social")
        territorial = AttentionType.objects.create(name="Territorial")
        AttentionSubtype.objects.create(name="Ayuda", attention_type=social)
        AttentionSubtype.objects.create(name="Luminaria", attention_type=territorial)
        self._login("superadmin")
        resp = self.client.get(reverse("attention_subtypes"), {"tipo": territorial.pk})
        self.assertEqual([row["cells"][1]["text"] for row in resp.context["rows"]], ["Luminaria"])
        resp = self.client.get(reverse("attention_subtypes"), {"tipo": 999999})
        self.assertEqual(len(resp.context["rows"]), 2)

    def test_delegaciones_filtro_por_comuna(self):
        self._login("superadmin")
        resp = self.client.get(reverse("delegations"), {"comuna": "Coquimbo"})
        self.assertEqual(self._first_column(resp), ["DEL02"])
        control = resp.context["filter_controls"][0]
        self.assertEqual([o["value"] for o in control["options"]], ["Coquimbo", "La Serena"])

    def test_exportacion_aplica_filtros_propios_y_orden(self):
        import io

        from openpyxl import load_workbook

        self._login("superadmin")
        resp = self.client.get(reverse("users_export"), {"rol": self.roles["ROL04"].pk, "orden": "-rut"})
        sheet = load_workbook(io.BytesIO(resp.content)).active
        self.assertEqual([r[0].value for r in sheet.iter_rows(min_row=2)],
                         ["11.111.114-4", "11.111.113-3"])


@override_settings(STORAGES=TEST_STORAGES)
class DatabaseSearchTests(_Base):
    def test_busqueda_devuelve_queryset_y_se_resuelve_en_sql(self):
        queryset = apply_search(Delegation.alive.all(), ("code", "name"), "centro")
        self.assertIsInstance(queryset, QuerySet)
        if connection.vendor == "sqlite":
            self.assertIn("sgr_normalizar", str(queryset.query))
        self.assertEqual(list(queryset.values_list("code", flat=True)), ["DEL01"])

    def test_sin_tildes_ni_mayusculas_y_varias_palabras(self):
        Delegation.objects.create(name="Las Compañías", code="DEL04")
        for query in ("companias", "COMPAÑIAS", "las   compañías", "LAS comp"):
            queryset = apply_search(Delegation.alive.all(), ("code", "name"), query)
            self.assertEqual(list(queryset.values_list("code", flat=True)), ["DEL04"], query)

    def test_busqueda_por_campo_relacionado(self):
        self._login("superadmin")
        resp = self.client.get(reverse("users"), {"q": "funcionario centro"})
        self.assertEqual(self._first_column(resp), ["11.111.113-3"])

    def test_paginar_no_trae_todas_las_filas(self):
        for i in range(4, 60):
            Delegation.objects.create(name=f"Extra {i}")
        self._login("superadmin")
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(reverse("delegations"), {"q": "extra"})
        self.assertEqual(len(resp.context["rows"]), 5)
        self.assertEqual(resp.context["total"], 56)
        # La consulta de la página usa LIMIT (no se cargan las 56 filas).
        self.assertTrue(any("LIMIT 5" in q["sql"] for q in ctx.captured_queries))


# ===========================================================================
# 2.4 Nombres de Excel y archivos con el código del registro
# ===========================================================================


@override_settings(STORAGES=TEST_STORAGES)
class ExportFilenameTests(_Base):
    def test_nombre_con_modulo_fecha_y_usuario(self):
        self._login("superadmin")
        for url_name, slug in (
            ("delegations_export", "delegaciones"), ("roles_export", "roles"),
            ("users_export", "usuarios"), ("items_export", "items"),
            ("attention_types_export", "tipos-atencion"),
            ("attention_subtypes_export", "sub-atenciones"),
            ("attentions_export", "atenciones"),
        ):
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, url_name)
            self.assertRegex(
                resp["Content-Disposition"],
                rf'^attachment; filename="{slug}_\d{{8}}_\d{{4}}_superadmin\.xlsx"$',
            )

    def test_usuario_con_correo_usa_la_parte_local(self):
        user = make_user("nora.paredes@ejemplo.cl")
        name = export_filename("usuarios", user)
        self.assertRegex(name, r"^usuarios_\d{8}_\d{4}_nora\.paredes\.xlsx$")

    def test_caracteres_raros_se_reemplazan(self):
        user = make_user("José Pérez/../x")
        self.assertRegex(export_filename("roles", user), r"^roles_\d{8}_\d{4}_[A-Za-z0-9._-]+\.xlsx$")


@override_settings(STORAGES=TEST_STORAGES, MEDIA_ROOT=MEDIA_TMP)
class CodePrefixedUploadTests(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(shutil.rmtree, MEDIA_TMP, ignore_errors=True)

    def test_imagen_de_atencion_lleva_el_numero(self):
        tipo = AttentionType.objects.create(name="Social")
        sub = AttentionSubtype.objects.create(name="Ayuda", attention_type=tipo)
        vecino = Neighbor.objects.create(identifier="22.222.222-2", full_name="Pedro Soto")
        attention = Attention.objects.create(
            neighbor=vecino, delegation=self.d1, attention_type=tipo,
            attention_subtype=sub, description="Descripción de prueba.",
            responsible=self.funcionario.user, evidence_image=png_file("evidencia.png"),
        )
        attention.refresh_from_db()
        self.assertRegex(
            attention.evidence_image.name,
            rf"^atenciones/imagenes/\d{{4}}/\d{{2}}/{attention.number}_evidencia[^/]*\.png$",
        )
        self.assertTrue(attention.evidence_image.storage.exists(attention.evidence_image.name))

    def test_ruta_de_adjunto_y_nombre_seguro(self):
        class Fake:
            number = "ATN-0042"

        path = attention_image_path(Fake(), "../../foto de visita.JPG")
        self.assertRegex(path, r"^atenciones/imagenes/\d{4}/\d{2}/ATN-0042_foto_de_visita\.JPG$")

    def test_evidencia_lleva_el_codigo_de_la_tarea(self):
        period = Period.objects.create(
            name="T1", quarter=1, start_date=date(2026, 1, 1), end_date=date(2026, 3, 31),
        )
        goal = InstitutionalGoal.objects.create(name="Meta", period=period, delegation=self.d1)
        task = Task.objects.create(goal=goal, title="Operativo", due_date=date(2026, 2, 1))
        activity = Activity.objects.create(task=task, name="Retiro", execution_date=date(2026, 2, 1))
        evidence = Evidence.objects.create(
            activity=activity, image_url="", file=SimpleUploadedFile("acta.pdf", b"%PDF-1.4 demo"),
        )
        # Ruta definida en main por el equipo: evidencias/<código de la tarea>/archivo.
        self.assertTrue(evidence.file.name.startswith(f"evidencias/{task.code}/acta"))
