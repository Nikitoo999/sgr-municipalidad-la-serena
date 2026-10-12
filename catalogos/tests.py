from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from sgr_core.test_utils import plain_static

from .models import AttentionSubtype, AttentionType


class CatalogModelTests(TestCase):
    def test_str(self):
        t = AttentionType.objects.create(name="Social")
        s = AttentionSubtype.objects.create(attention_type=t, name="Ayuda directa")
        self.assertEqual(str(t), "Social")
        self.assertEqual(str(s), "Social › Ayuda directa")

    def test_tipo_nombre_unico(self):
        AttentionType.objects.create(name="Social")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttentionType.objects.create(name="Social")

    def test_subatencion_unica_por_tipo_pero_repetible_entre_tipos(self):
        a = AttentionType.objects.create(name="A")
        b = AttentionType.objects.create(name="B")
        AttentionSubtype.objects.create(attention_type=a, name="X")
        AttentionSubtype.objects.create(attention_type=b, name="X")  # otro tipo: OK
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttentionSubtype.objects.create(attention_type=a, name="X")


@plain_static
class CatalogAdminCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("root", "root@ejemplo.cl", "Clave-Test-123")
        cls.plain = User.objects.create_user("plain", password="Clave-Test-123", is_staff=True)

    def setUp(self):
        self.client.force_login(self.admin)

    def _inline_mgmt(self):
        return {
            "subtypes-TOTAL_FORMS": "0", "subtypes-INITIAL_FORMS": "0",
            "subtypes-MIN_NUM_FORMS": "0", "subtypes-MAX_NUM_FORMS": "1000",
        }

    def test_crear_tipo(self):
        data = {"name": "Social", "description": "d", "is_active": "on", **self._inline_mgmt()}
        r = self.client.post(reverse("admin:catalogos_attentiontype_add"), data)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(AttentionType.objects.filter(name="Social").exists())

    def test_tipo_duplicado_sin_distinguir_mayusculas(self):
        AttentionType.objects.create(name="Social")
        data = {"name": "  social ", "description": "", **self._inline_mgmt()}
        r = self.client.post(reverse("admin:catalogos_attentiontype_add"), data)
        self.assertEqual(r.status_code, 200)  # vuelve al formulario con error
        self.assertContains(r, "Ya existe un Tipo de Atención")
        self.assertEqual(AttentionType.objects.count(), 1)

    def test_crear_editar_y_listar_subatencion(self):
        t = AttentionType.objects.create(name="Social")
        r = self.client.post(reverse("admin:catalogos_attentionsubtype_add"),
                             {"attention_type": t.pk, "name": "Visita", "description": "", "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        s = AttentionSubtype.objects.get(name="Visita")
        r = self.client.post(reverse("admin:catalogos_attentionsubtype_change", args=[s.pk]),
                             {"attention_type": t.pk, "name": "Visita domiciliaria", "description": "", "is_active": "on"})
        self.assertEqual(r.status_code, 302)
        s.refresh_from_db()
        self.assertEqual(s.name, "Visita domiciliaria")
        r = self.client.get(reverse("admin:catalogos_attentionsubtype_changelist") + "?q=domiciliaria")
        self.assertContains(r, "Visita domiciliaria")

    def test_subatencion_duplicada_en_mismo_tipo(self):
        t = AttentionType.objects.create(name="Social")
        AttentionSubtype.objects.create(attention_type=t, name="Visita")
        r = self.client.post(reverse("admin:catalogos_attentionsubtype_add"),
                             {"attention_type": t.pk, "name": "visita", "description": ""})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "ya tiene una sub atención")

    def test_listado_tipos_muestra_contador(self):
        t = AttentionType.objects.create(name="Social")
        AttentionSubtype.objects.create(attention_type=t, name="A")
        AttentionSubtype.objects.create(attention_type=t, name="B")
        r = self.client.get(reverse("admin:catalogos_attentiontype_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Social")

    def test_no_se_borra_tipo_con_subatenciones(self):
        t = AttentionType.objects.create(name="Social")
        AttentionSubtype.objects.create(attention_type=t, name="A")
        r = self.client.post(reverse("admin:catalogos_attentiontype_delete", args=[t.pk]), {"post": "yes"})
        self.assertTrue(AttentionType.objects.filter(pk=t.pk).exists())
        self.assertEqual(r.status_code, 200)

    def test_borrar_tipo_sin_subatenciones(self):
        t = AttentionType.objects.create(name="Vacío")
        r = self.client.post(reverse("admin:catalogos_attentiontype_delete", args=[t.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(AttentionType.objects.filter(pk=t.pk).exists())

    def test_usuario_staff_sin_permisos_no_accede(self):
        self.client.force_login(self.plain)
        r = self.client.get(reverse("admin:catalogos_attentiontype_changelist"))
        self.assertEqual(r.status_code, 403)
