from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import RedirectView

from . import views_auth as va
from . import views_crud as vc
from .views import dashboard

def crud(prefix, slug, List, Detail, Create, Update, Delete):
    return [
        path(f"gestion/{slug}/", List.as_view(), name=f"{prefix}_list"),
        path(f"gestion/{slug}/nuevo/", Create.as_view(), name=f"{prefix}_create"),
        path(f"gestion/{slug}/<int:pk>/", Detail.as_view(), name=f"{prefix}_detail"),
        path(f"gestion/{slug}/<int:pk>/editar/", Update.as_view(), name=f"{prefix}_update"),
        path(f"gestion/{slug}/<int:pk>/desactivar/", Delete.as_view(), name=f"{prefix}_delete"),
    ]

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
    path("dashboard/", dashboard, name="dashboard"),
    path("login/", va.SgrLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("delegacion-activa/", va.switch_delegation, name="switch_delegation"),
    path("recuperar/", va.password_reset_request, name="password_reset_request"),
    path("recuperar/verificar/", va.password_reset_verify, name="password_reset_verify"),
    path("recuperar/reenviar/", va.password_reset_resend, name="password_reset_resend"),
    path("recuperar/nueva-clave/", va.password_reset_confirm, name="password_reset_confirm"),
]
urlpatterns += crud("delegation", "delegaciones", vc.DelegationList, vc.DelegationDetail, vc.DelegationCreate, vc.DelegationUpdate, vc.DelegationDelete)
urlpatterns += crud("role", "roles", vc.RoleList, vc.RoleDetail, vc.RoleCreate, vc.RoleUpdate, vc.RoleDelete)
urlpatterns += crud("user", "usuarios", vc.UserList, vc.UserDetail, vc.UserCreate, vc.UserUpdate, vc.UserDelete)
