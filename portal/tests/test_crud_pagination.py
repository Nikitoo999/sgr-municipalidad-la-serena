"""Pruebas nuevas de paginación del motor CRUD (Fase 2).

Escritas ANTES de la corrección: las de href explícito de la página 1
deben FALLAR con el código actual; la de seguir "Anterior" documenta si
la causa es de la vista o del navegador.
"""
import html
import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from sgr_core.models import Delegation, Role, RolePermission
from sgr_core.roles import ensure_base_roles

from portal.tests.utils import TEST_STORAGES


@override_settings(STORAGES=TEST_STORAGES)
class CrudPaginationHrefTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_base_roles(Role, RolePermission)
        cls.d1 = Delegation.objects.create(
            name="Centro", code="DEL01", commune="La Serena",
            address="Calle Principal 1", color="#C62828",
        )
        cls.d2 = Delegation.objects.create(
            name="Avenida del Mar", code="DEL02", commune="La Serena",
            address="Av. Costanera 2", color="#1D6FA5",
        )
        cls.d3 = Delegation.objects.create(
            name="Las Compañías", code="DEL03", commune="La Serena",
            address="Calle Secundaria 3", color="#6A1B9A",
        )
        cls.d4 = Delegation.objects.create(
            name="Sector Cerrado", code="DEL04", status="Inactiva",
        )
        User.objects.create_user(
            username="superadmin", password="Demo2026!",
            is_superuser=True, is_staff=True,
        )
    def _extras(self, count=8):
        for i in range(5, 5 + count):
            Delegation.objects.create(
                name=f"Paginado {i}", code=f"PAG{i:02d}",
                commune="La Serena",
            )

    def _pager_hrefs(self, content):
        """Texto del enlace -> href (solo <a>, no spans deshabilitados)."""
        links = {}
        pattern = re.compile(
            r'<a class="pg" href="([^"]*)"[^>]*>([^<]*)</a>'
        )
        for match in pattern.finditer(content):
            links[match.group(2).strip()] = html.unescape(match.group(1))
        return links

    def test_numero_1_lleva_page_explicito_sin_filtros(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(reverse("delegations"), {"page": 2})
        self.assertEqual(resp.status_code, 200)
        hrefs = self._pager_hrefs(resp.content.decode())
        href1 = hrefs.get("1")
        self.assertIn("page=1", href1 or "", f"href del '1': {href1!r}")

    def test_numero_1_lleva_page_explicito_con_filtros(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(
            reverse("delegations"),
            {"q": "paginado", "estado": "Activa", "page": 2},
        )
        self.assertEqual(resp.status_code, 200)
        hrefs = self._pager_hrefs(resp.content.decode())
        href1 = hrefs.get("1")
        self.assertIn("page=1", href1 or "", f"href del '1': {href1!r}")
        self.assertIn("q=paginado", href1 or "")
        self.assertIn("estado=Activa", href1 or "")

    def test_seguir_anterior_desde_pagina_2_da_pagina_1(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(reverse("delegations"), {"page": 2})
        hrefs = self._pager_hrefs(resp.content.decode())
        prev = hrefs.get("Anterior")
        self.assertIsNotNone(prev, "debe existir enlace 'Anterior' en p2")
        follow = self.client.get(reverse("delegations") + prev)
        self.assertContains(follow, "Mostrando 1 a 5 de")

    def test_seguir_numero_1_desde_pagina_2_da_pagina_1(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(reverse("delegations"), {"page": 2})
        hrefs = self._pager_hrefs(resp.content.decode())
        href1 = hrefs.get("1")
        self.assertIsNotNone(href1, "debe existir enlace '1' en p2")
        follow = self.client.get(reverse("delegations") + href1)
        self.assertContains(follow, "Mostrando 1 a 5 de")

    def test_enlaces_conservan_q_y_estado(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(
            reverse("delegations"),
            {"q": "paginado", "estado": "Activa", "page": 2},
        )
        hrefs = self._pager_hrefs(resp.content.decode())
        for label, href in hrefs.items():
            self.assertIn("q=paginado", href, f"enlace {label!r} pierde q")
            self.assertIn("estado=Activa", href, f"enlace {label!r} pierde estado")

    def test_extremos_deshabilitados(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        first = self.client.get(reverse("delegations"), {"page": 1}).content.decode()
        self.assertIn('<span class="pg" aria-disabled="true">Anterior</span>', first)
        last = self.client.get(reverse("delegations"), {"page": 3}).content.decode()
        self.assertIn('<span class="pg" aria-disabled="true">Siguiente</span>', last)

    def test_page_fuera_de_rango_e_invalida(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        out = self.client.get(reverse("delegations"), {"page": 999})
        self.assertEqual(out.status_code, 200)
        self.assertContains(out, "Mostrando 11 a 12 de 12 registros")
        bad = self.client.get(reverse("delegations"), {"page": "abc"})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "Mostrando 1 a 5 de 12 registros")

    def test_buscar_desde_pagina_3_vuelve_a_pagina_1(self):
        # El formulario de búsqueda envía solo q+estado (sin page).
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(
            reverse("delegations"), {"q": "paginado"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Mostrando 1 a 5 de 8 registros")

    def test_mostrando_x_a_y_en_cada_pagina(self):
        self._extras()
        self.client.login(username="superadmin", password="Demo2026!")
        self.assertContains(
            self.client.get(reverse("delegations"), {"page": 1}),
            "Mostrando 1 a 5 de 12 registros",
        )
        self.assertContains(
            self.client.get(reverse("delegations"), {"page": 2}),
            "Mostrando 6 a 10 de 12 registros",
        )
        self.assertContains(
            self.client.get(reverse("delegations"), {"page": 3}),
            "Mostrando 11 a 12 de 12 registros",
        )

    def test_mensajes_serializados_una_sola_vez(self):
        self.client.login(username="superadmin", password="Demo2026!")
        resp = self.client.get(reverse("delegations"))
        content = resp.content.decode()
        self.assertEqual(content.count('id="sgr-messages-data"'), 1)
        self.assertNotIn('class="alert', content)
