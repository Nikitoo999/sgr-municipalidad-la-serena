from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from django.views.generic import RedirectView

from .views import dashboard

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("dashboard/", dashboard, name="dashboard"),
    path("login/", LoginView.as_view(template_name="portal/login.html"), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
]
