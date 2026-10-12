"""CRUD de Delegaciones, Roles y Usuarios con permisos y alcance validados en el servidor."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from operaciones.models import Employee
from sgr_core.models import Delegation, Role
from .access import BASE_ROLE_CODES, allowed_delegations, assignable_role_codes, has_perm
from .forms import DelegationForm, EmployeeUserForm, RoleForm


class CrudMixin(LoginRequiredMixin):
    required_permission = None
    entity = ""            # nombre en singular para mensajes
    url_prefix = ""        # prefijo de nombres de URL: <prefix>_list, _create, ...
    perm_prefix = ""       # 'role', 'user', 'delegation'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_perm(request.user, self.required_permission):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def scoped_queryset(self):
        raise NotImplementedError

    def get_queryset(self):
        return self.scoped_queryset()

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        u = self.request.user
        ctx.update(entity=self.entity, url_prefix=self.url_prefix,
                can_create=has_perm(u, f"{self.perm_prefix}.create"),
                can_edit=has_perm(u, f"{self.perm_prefix}.edit"),
                can_delete=has_perm(u, f"{self.perm_prefix}.delete"))
        return ctx

    def success_url_list(self):
        return reverse(f"{self.url_prefix}_list")


class CrudList(CrudMixin, ListView):
    template_name = "portal/crud_list.html"
    paginate_by = 10
    search_fields = ()
    active_lookup = "is_active"
    ordering = ("pk",)
    columns = ()
    title = ""

    def base_queryset(self):
        return self.scoped_queryset()

    def get_queryset(self):
        qs = self.base_queryset()
        # Búsqueda parcial, sin distinguir mayúsculas: todos los términos deben aparecer en algún campo.
        for term in self.request.GET.get("q", "").split():
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": term})
            qs = qs.filter(cond)
        estado = self.request.GET.get("estado")
        if estado == "activo":
            qs = qs.filter(**{self.active_lookup: True})
        elif estado == "inactivo":
            qs = qs.filter(**{self.active_lookup: False})
        return qs.distinct().order_by(*self.ordering)

    def cells(self, obj):
        raise NotImplementedError

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(title=self.title, columns=self.columns, querystring=params.urlencode(),
                q=self.request.GET.get("q", ""), estado=self.request.GET.get("estado", ""),
                total=ctx["paginator"].count,
                rows=[{"pk": o.pk, "cells": self.cells(o)} for o in ctx["object_list"]])
        return ctx


class CrudDetail(CrudMixin, DetailView):
    template_name = "portal/crud_detail.html"

    def fields(self, obj):
        raise NotImplementedError

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["fields"] = self.fields(self.object)
        ctx["title"] = f"{self.entity}: {self.object}"
        return ctx


class CrudForm:
    template_name = "portal/crud_form.html"

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["title"] = ("Editar " if getattr(self, "object", None) and self.object.pk else "Nuevo ") + self.entity.lower()
        return ctx

    def get_success_url(self):
        return self.success_url_list()


class CrudDelete(CrudMixin, View):
    """Desactivación lógica (no se borra físicamente) con validación de integridad."""
    http_method_names = ["post"]

    def get_object(self):
        obj = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if obj is None:
            raise Http404
        return obj

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        error = self.deactivate(obj)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, f"{self.entity} desactivado(a) correctamente.")
        return redirect(self.success_url_list())


# =============================== Delegaciones ===============================
class DelegationBase(CrudMixin):
    entity, url_prefix, perm_prefix = "Delegación", "delegation", "delegation"

    def scoped_queryset(self):
        return allowed_delegations(self.request.user)


class DelegationList(DelegationBase, CrudList):
    required_permission = "delegation.view"
    title = "Delegaciones municipales"
    search_fields = ("code", "name", "commune", "address")
    ordering = ("code", "name")
    columns = ("Código", "Nombre", "Comuna", "Estado")

    def cells(self, o):
        return [o.code or "—", o.name, o.commune, "Activa" if o.is_active else "Inactiva"]


class DelegationDetail(DelegationBase, CrudDetail):
    required_permission = "delegation.view"

    def fields(self, o):
        return [("Código", o.code or "—"), ("Nombre", o.name), ("Dirección", o.address or "—"), ("Comuna", o.commune),
                ("Descripción", o.description or "—"), ("Estado", "Activa" if o.is_active else "Inactiva")]


class DelegationCreate(DelegationBase, CrudForm, CreateView):
    required_permission = "delegation.create"
    form_class = DelegationForm

    def form_valid(self, form):
        messages.success(self.request, "Delegación creada correctamente.")
        return super().form_valid(form)


class DelegationUpdate(DelegationBase, CrudForm, UpdateView):
    required_permission = "delegation.edit"
    form_class = DelegationForm

    def form_valid(self, form):
        if not form.cleaned_data["is_active"] and Employee.objects.filter(
                delegation=self.object, deleted_at__isnull=True, user__is_active=True).exists():
            form.add_error("is_active", "No se puede desactivar: tiene usuarios activos asignados.")
            return self.form_invalid(form)
        messages.success(self.request, "Delegación actualizada correctamente.")
        return super().form_valid(form)


class DelegationDelete(DelegationBase, CrudDelete):
    required_permission = "delegation.delete"

    def deactivate(self, obj):
        if Employee.objects.filter(delegation=obj, deleted_at__isnull=True, user__is_active=True).exists():
            return "No se puede desactivar la delegación: tiene usuarios activos asignados."
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])


# ==================================== Roles ====================================
class RoleBase(CrudMixin):
    entity, url_prefix, perm_prefix = "Rol", "role", "role"

    def scoped_queryset(self):
        return Role.objects.filter(deleted_at__isnull=True)


class RoleList(RoleBase, CrudList):
    required_permission = "role.view"
    title = "Roles y permisos"
    search_fields = ("code", "name", "description")
    ordering = ("code",)
    columns = ("Código", "Rol", "Alcance", "Permisos", "Estado")

    def base_queryset(self):
        return self.scoped_queryset().prefetch_related("permissions")

    def cells(self, o):
        return [o.code, o.name, o.get_scope_display(), str(o.permissions.count()), "Activo" if o.is_active else "Inactivo"]


class RoleDetail(RoleBase, CrudDetail):
    required_permission = "role.view"

    def fields(self, o):
        return [("Código", o.code), ("Nombre", o.name), ("Descripción", o.description or "—"),
                ("Alcance autorizado", o.get_scope_display()),
                ("Permisos", ", ".join(p.name for p in o.permissions.all()) or "Ninguno"),
                ("Estado", "Activo" if o.is_active else "Inactivo")]


class RoleCreate(RoleBase, CrudForm, CreateView):
    required_permission = "role.create"
    form_class = RoleForm

    def form_valid(self, form):
        messages.success(self.request, "Rol creado correctamente.")
        return super().form_valid(form)


class RoleUpdate(RoleBase, CrudForm, UpdateView):
    required_permission = "role.edit"
    form_class = RoleForm

    def form_valid(self, form):
        if not form.cleaned_data["is_active"] and Employee.objects.filter(
                app_role=self.object, deleted_at__isnull=True, user__is_active=True).exists():
            form.add_error("is_active", "No se puede desactivar: hay usuarios activos con este rol.")
            return self.form_invalid(form)
        messages.success(self.request, "Rol actualizado correctamente.")
        return super().form_valid(form)


class RoleDelete(RoleBase, CrudDelete):
    required_permission = "role.delete"

    def deactivate(self, obj):
        if obj.code in BASE_ROLE_CODES:
            return "Los roles base del sistema no se pueden desactivar."
        if Employee.objects.filter(app_role=obj, deleted_at__isnull=True, user__is_active=True).exists():
            return "No se puede desactivar el rol: hay usuarios activos que lo utilizan."
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])


# =================================== Usuarios ===================================
class UserBase(CrudMixin):
    entity, url_prefix, perm_prefix = "Usuario", "user", "user"

    def scoped_queryset(self):
        """Solo usuarios de delegaciones autorizadas y con rol que el actor puede gestionar."""
        qs = Employee.objects.filter(deleted_at__isnull=True, delegation__in=allowed_delegations(self.request.user))
        if not self.request.user.is_superuser:
            qs = qs.filter(Q(app_role__isnull=True) | Q(app_role__code__in=assignable_role_codes(self.request.user)))
        return qs.select_related("user", "delegation", "app_role")


class UserList(UserBase, CrudList):
    required_permission = "user.view"
    title = "Usuarios del sistema"
    active_lookup = "user__is_active"
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email",
                    "rut", "app_role__name", "delegation__name", "delegation__code")
    ordering = ("user__first_name", "user__last_name")
    columns = ("Nombre", "Correo", "Rol", "Delegación", "Estado")

    def cells(self, o):
        return [o.user.get_full_name() or o.user.username, o.user.email, o.app_role.name if o.app_role else "Sin rol",
                str(o.delegation), "Activo" if o.user.is_active else "Inactivo"]


class UserDetail(UserBase, CrudDetail):
    required_permission = "user.view"

    def fields(self, o):
        return [("Usuario", o.user.username), ("Nombre", o.user.get_full_name()), ("Correo", o.user.email),
                ("RUT", o.rut), ("Teléfono", o.phone or "—"), ("Dirección", o.address or "—"),
                ("Rol", o.app_role.name if o.app_role else "Sin rol"), ("Delegación principal", str(o.delegation)),
                ("Otras delegaciones", ", ".join(str(d) for d in o.authorized_delegations.all()) or "Ninguna"),
                ("Estado", "Activo" if o.user.is_active else "Inactivo")]


class UserFormMixin(CrudForm):
    form_class = EmployeeUserForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["actor"] = self.request.user
        return kw


class UserCreate(UserBase, UserFormMixin, CreateView):
    required_permission = "user.create"

    def form_valid(self, form):
        messages.success(self.request, "Usuario creado correctamente.")
        return super().form_valid(form)


class UserUpdate(UserBase, UserFormMixin, UpdateView):
    required_permission = "user.edit"

    def form_valid(self, form):
        messages.success(self.request, "Usuario actualizado correctamente.")
        return super().form_valid(form)


class UserDelete(UserBase, CrudDelete):
    required_permission = "user.delete"

    def deactivate(self, obj):
        if obj.user_id == self.request.user.pk:
            return "No puedes desactivar tu propia cuenta."
        with transaction.atomic():
            obj.user.is_active = False
            obj.user.save(update_fields=["is_active"])
        return None
