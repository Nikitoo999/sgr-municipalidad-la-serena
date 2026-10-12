from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from operaciones.models import Employee
from portal.models import PasswordResetCode
from sgr_core.models import Delegation, Role
from django.core.management import call_command

User = get_user_model()
PWD = "Clave-Segura-2026!"


def make_user(username, role_code, delegation, email=None, rut=None, active=True):
    u = User.objects.create_user(username, email or f"{username}@example.test", PWD, is_active=active, first_name=username.title(), last_name="Test")
    Employee.objects.create(user=u, rut=rut or f"1{abs(hash(username)) % 10**7}-K", delegation=delegation,
                            app_role=Role.objects.get(code=role_code))
    return u

@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})

class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_roles", verbosity=0)
        cls.d1 = Delegation.objects.create(code="DEL01", name="Centro")
        cls.d2 = Delegation.objects.create(code="DEL02", name="Norte")
        cls.admin = make_user("admin1", "superadministrador", cls.d1)
        cls.coord = make_user("coord1", "coordinador", cls.d1)
        cls.deleg = make_user("deleg1", "delegado_municipal", cls.d1)
        cls.func = make_user("func1", "funcionario", cls.d1)
        cls.func2 = make_user("func2", "funcionario", cls.d2)


class LoginTests(BaseCase):
    def test_login_con_usuario_y_con_correo_sin_importar_mayusculas(self):
        for ident in ("func1", "FUNC1", "func1@example.test", "Func1@Example.Test"):
            r = self.client.post(reverse("login"), {"username": ident, "password": PWD})
            self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)
            self.client.logout()

    def test_credenciales_incorrectas_y_campos_vacios(self):
        r = self.client.post(reverse("login"), {"username": "func1", "password": "mala"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "incorrectos")
        r = self.client.post(reverse("login"), {"username": "", "password": ""})
        self.assertEqual(r.status_code, 200)

    def test_cuenta_inactiva_no_ingresa(self):
        make_user("inactivo", "funcionario", self.d1, active=False)
        r = self.client.post(reverse("login"), {"username": "inactivo", "password": PWD})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ruta_protegida_redirige_a_login(self):
        r = self.client.get(reverse("user_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r.url)


class PermissionTests(BaseCase):
    def get(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args))

    def test_funcionario_no_accede_a_crud_sensibles(self):
        for name in ("role_list", "user_list", "delegation_create", "role_create", "user_create"):
            self.assertEqual(self.get(self.func, name).status_code, 403, name)

    def test_post_directo_sin_permiso_es_403(self):
        self.client.force_login(self.func)
        r = self.client.post(reverse("user_delete", args=[self.func2.employee.pk]))
        self.assertEqual(r.status_code, 403)

    def test_solo_superadmin_modifica_roles_y_delegaciones(self):
        for u in (self.coord, self.deleg):
            self.assertEqual(self.get(u, "role_create").status_code, 403)
            self.assertEqual(self.get(u, "delegation_create").status_code, 403)
        self.assertEqual(self.get(self.admin, "role_create").status_code, 200)
        self.assertEqual(self.get(self.admin, "delegation_create").status_code, 200)

    def test_delegado_solo_ve_usuarios_de_su_delegacion(self):
        r = self.get(self.deleg, "user_list")
        names = [row["cells"][0] for row in r.context["rows"]]
        self.assertIn("Func1 Test", names)
        self.assertNotIn("Func2 Test", names)

    def test_delegado_no_accede_por_url_a_usuario_de_otra_delegacion(self):
        self.assertEqual(self.get(self.deleg, "user_detail", self.func2.employee.pk).status_code, 404)
        self.client.force_login(self.deleg)
        r = self.client.post(reverse("user_update", args=[self.func2.employee.pk]), {})
        self.assertEqual(r.status_code, 404)

    def test_delegado_no_puede_asignar_rol_superior(self):
        self.client.force_login(self.deleg)
        r = self.client.get(reverse("user_create"))
        roles = {x.code for x in r.context["form"].fields["app_role"].queryset}
        self.assertEqual(roles, {"funcionario"})

    def test_cambio_de_delegacion_solo_a_autorizadas(self):
        self.client.force_login(self.func)
        self.client.post(reverse("switch_delegation"), {"delegation": self.d2.pk})
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["sgr_active_delegation"], self.d1)

    def test_delegacion_multiple_autorizada(self):
        self.deleg.employee.authorized_delegations.add(self.d2)
        self.client.force_login(self.deleg)
        self.client.post(reverse("switch_delegation"), {"delegation": self.d2.pk})
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["sgr_active_delegation"], self.d2)


class CrudTests(BaseCase):
    def test_busqueda_parcial_sin_mayusculas_y_filtros_en_paginacion(self):
        for i in range(25):
            Delegation.objects.create(code=f"X{i:02d}", name=f"Sector Prueba {i}")
        self.client.force_login(self.admin)
        r = self.client.get(reverse("delegation_list"), {"q": "sEcToR pru", "page": 2})
        self.assertEqual(r.context["total"], 25)
        self.assertIn("q=sEcToR+pru", r.context["querystring"])
        self.assertEqual(len(r.context["rows"]), 10)

    def test_crear_delegacion_duplicada_es_rechazada(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("delegation_create"), {"code": "del01", "name": "Otra", "commune": "La Serena", "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["form"].errors.get("code"))

    def test_no_se_desactiva_delegacion_con_usuarios_activos(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("delegation_delete", args=[self.d1.pk]))
        self.d1.refresh_from_db()
        self.assertTrue(self.d1.is_active)

    def test_roles_base_no_se_desactivan(self):
        self.client.force_login(self.admin)
        role = Role.objects.get(code="funcionario")
        self.client.post(reverse("role_delete", args=[role.pk]))
        role.refresh_from_db()
        self.assertTrue(role.is_active)

    def test_crear_usuario_valida_correo_duplicado_y_clave(self):
        self.client.force_login(self.admin)
        base = {"username": "nuevo", "first_name": "N", "last_name": "U", "email": "FUNC1@example.test", "rut": "11111111-1",
                "app_role": Role.objects.get(code="funcionario").pk, "delegation": self.d1.pk,
                "is_active": "on", "password1": PWD, "password2": PWD}
        r = self.client.post(reverse("user_create"), base)
        self.assertTrue(r.context["form"].errors.get("email"))
        base["email"] = "nuevo@example.test"
        base["password2"] = "otra"
        r = self.client.post(reverse("user_create"), base)
        self.assertTrue(r.context["form"].errors.get("password2"))
        base["password2"] = PWD
        r = self.client.post(reverse("user_create"), base)
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(username="nuevo")
        self.assertTrue(u.check_password(PWD))
        self.assertNotEqual(u.password, PWD)  # almacenada con hash

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_delete", args=[self.admin.employee.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)


class PasswordResetTests(BaseCase):
    def request_code(self, email="func1@example.test"):
        self.client.post(reverse("password_reset_request"), {"email": email})

    def code_from_mail(self):
        return mail.outbox[-1].body.split("Tu código es: ")[1][:6]

    def test_respuesta_identica_exista_o_no_el_correo(self):
        r1 = self.client.post(reverse("password_reset_request"), {"email": "func1@example.test"}, follow=True)
        self.client.logout()
        r2 = self.client.post(reverse("password_reset_request"), {"email": "noexiste@example.test"}, follow=True)
        self.assertEqual(r1.redirect_chain, r2.redirect_chain)
        self.assertEqual([str(m) for m in r1.context["messages"]], [str(m) for m in r2.context["messages"]])
        self.assertEqual(len(mail.outbox), 1)

    def test_flujo_completo_y_codigo_no_reutilizable(self):
        self.request_code()
        code = self.code_from_mail()
        self.assertFalse(PasswordResetCode.objects.filter(code_hash=code).exists())  # no se guarda en claro
        r = self.client.post(reverse("password_reset_verify"), {"code": code})
        self.assertRedirects(r, reverse("password_reset_confirm"))
        new = "OtraClave-Distinta-77!"
        r = self.client.post(reverse("password_reset_confirm"), {"new_password1": new, "new_password2": new})
        self.assertRedirects(r, reverse("login"))
        self.assertTrue(self.client.login(username="func1", password=new))
        self.client.logout()
        self.assertFalse(self.client.login(username="func1", password=PWD))
        # código ya utilizado: no sirve y la pantalla de nueva clave queda cerrada
        r = self.client.post(reverse("password_reset_verify"), {"code": code})
        self.assertEqual(r.status_code, 302)  # sin sesión de recuperación -> vuelve a solicitar
        self.assertEqual(self.client.get(reverse("password_reset_confirm")).status_code, 302)

    def test_nueva_clave_bloqueada_sin_verificar(self):
        self.assertEqual(self.client.get(reverse("password_reset_confirm")).status_code, 302)

    def test_codigo_incorrecto_y_bloqueo_por_intentos(self):
        self.request_code()
        good = self.code_from_mail()
        bad = "000000" if good != "000000" else "111111"
        for _ in range(5):
            r = self.client.post(reverse("password_reset_verify"), {"code": bad})
            self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse("password_reset_verify"), {"code": good})  # ya bloqueado
        self.assertEqual(r.status_code, 200)

    def test_codigo_vencido(self):
        self.request_code()
        code = self.code_from_mail()
        PasswordResetCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        r = self.client.post(reverse("password_reset_verify"), {"code": code})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("password_reset_confirm")).status_code, 302)

    def test_reenvio_respeta_espera_y_luego_invalida_el_anterior(self):
        self.request_code()
        old = self.code_from_mail()
        self.client.post(reverse("password_reset_resend"))
        self.assertEqual(len(mail.outbox), 1)  # dentro de los 45 s no reenvía
        PasswordResetCode.objects.update(created_at=timezone.now() - timedelta(seconds=60))
        session = self.client.session
        session["pr_sent_at"] = (timezone.now() - timedelta(seconds=60)).timestamp()
        session.save()
        self.client.post(reverse("password_reset_resend"))
        self.assertEqual(len(mail.outbox), 2)
        new = self.code_from_mail()
        if new != old:
            r = self.client.post(reverse("password_reset_verify"), {"code": old})
            self.assertEqual(r.status_code, 200)
