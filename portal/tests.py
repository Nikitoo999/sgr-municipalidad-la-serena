import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from sgr_core.test_utils import plain_static


@plain_static
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ana", "ana@ejemplo.cl", "Clave-Test-123")

    def test_dashboard_exige_login(self):
        r = self.client.get(reverse("dashboard"))
        self.assertRedirects(r, "/login/?next=/dashboard/")

    def test_login_correcto_y_dashboard(self):
        r = self.client.post(reverse("login"), {"username": "ana", "password": "Clave-Test-123"})
        self.assertRedirects(r, reverse("dashboard"))
        self.assertContains(self.client.get(reverse("dashboard")), "Bienvenido")

    def test_login_incorrecto(self):
        r = self.client.post(reverse("login"), {"username": "ana", "password": "mala"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_tiene_enlace_de_recuperacion(self):
        self.assertContains(self.client.get(reverse("login")), reverse("password_reset"))


@plain_static
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ana", "ana@ejemplo.cl", "Clave-Test-123")

    def test_flujo_completo_de_recuperacion(self):
        r = self.client.post(reverse("password_reset"), {"email": "ana@ejemplo.cl"})
        self.assertRedirects(r, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["ana@ejemplo.cl"])
        self.assertIn("Recuperación de contraseña", msg.subject)
        link = re.search(r"http://testserver(/password-reset/confirmar/\S+)", msg.body).group(1)

        r = self.client.get(link, follow=True)       # Django redirige al token "set-password"
        self.assertContains(r, "Escriba su nueva contraseña")
        post_url = r.redirect_chain[-1][0]
        r = self.client.post(post_url, {"new_password1": "OtraClave-Segura-987",
                                        "new_password2": "OtraClave-Segura-987"})
        self.assertRedirects(r, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OtraClave-Segura-987"))
        # el enlace ya no sirve
        self.assertContains(self.client.get(link, follow=True), "no es válido")

    def test_correo_inexistente_no_revela_nada_ni_envia(self):
        r = self.client.post(reverse("password_reset"), {"email": "nadie@ejemplo.cl"})
        self.assertRedirects(r, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_usuario_inactivo_no_recibe_correo(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(reverse("password_reset"), {"email": "ana@ejemplo.cl"})
        self.assertEqual(len(mail.outbox), 0)

    def test_token_invalido(self):
        r = self.client.get("/password-reset/confirmar/abc/xyz-123/", follow=True)
        self.assertContains(r, "no es válido")

    def test_contrasena_debil_rechazada(self):
        self.client.post(reverse("password_reset"), {"email": "ana@ejemplo.cl"})
        link = re.search(r"http://testserver(/password-reset/confirmar/\S+)", mail.outbox[0].body).group(1)
        r = self.client.get(link, follow=True)
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(r.status_code, 200)   # no avanza
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Clave-Test-123"))
