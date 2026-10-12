from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import RedirectView

from .views import dashboard

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("dashboard/", dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="portal/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    # Recuperación de contraseña por correo (envío: ver settings EMAIL_* y docs/CORREO_AWS_SES.md)
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="portal/password_reset_form.html",
        email_template_name="portal/password_reset_email.txt",
        subject_template_name="portal/password_reset_subject.txt",
        success_url=reverse_lazy("password_reset_done"),
    ), name="password_reset"),
    path("password-reset/enviado/", auth_views.PasswordResetDoneView.as_view(
        template_name="portal/password_reset_done.html",
    ), name="password_reset_done"),
    path("password-reset/confirmar/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="portal/password_reset_confirm.html",
        success_url=reverse_lazy("password_reset_complete"),
    ), name="password_reset_confirm"),
    path("password-reset/listo/", auth_views.PasswordResetCompleteView.as_view(
        template_name="portal/password_reset_complete.html",
    ), name="password_reset_complete"),
]
