from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from operaciones.models import Employee
from sgr_core.models import Delegation, Role, Permission
from .access import (BASE_ROLE_CODES, FUNCIONARIO, DELEGADO, COORDINADOR, SUPERADMIN,
                    allowed_delegations, assignable_role_codes, get_employee, get_role)

User = get_user_model()


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Usuario o correo", max_length=254,
                            widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    error_messages = {
        "invalid_login": "Usuario/correo o contraseña incorrectos. Revisa los datos e inténtalo nuevamente.",
        "inactive": "Tu cuenta no está habilitada. Contacta al administrador.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_superuser:
            return
        emp = get_employee(user)
        if not emp or not get_role(user):
            raise ValidationError("Tu cuenta no tiene un perfil activo. Contacta al administrador.", code="no_profile")


class ResetRequestForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico", max_length=254)


class ResetCodeForm(forms.Form):
    code = forms.CharField(label="Código de 6 dígitos", max_length=20)

    def clean_code(self):
        digits = "".join(ch for ch in self.cleaned_data["code"] if ch.isdigit())
        if len(digits) != 6:
            raise ValidationError("Ingresa el código de 6 dígitos.")
        return digits


# ------------------------------- Delegaciones -------------------------------
class DelegationForm(forms.ModelForm):
    class Meta:
        model = Delegation
        fields = ["code", "name", "address", "commune", "description", "color", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "color": forms.TextInput(attrs={"placeholder": "#C62828"})}

    def _unique_ci(self, field, value, label):
        qs = Delegation.objects.filter(**{f"{field}__iexact": value}, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Ya existe una delegación con ese {label}.")
        return value

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise ValidationError("El código es obligatorio.")
        return self._unique_ci("code", code, "código")

    def clean_name(self):
        return self._unique_ci("name", self.cleaned_data["name"].strip(), "nombre")

    def clean_color(self):
        color = (self.cleaned_data.get("color") or "").strip()
        if color and (len(color) != 7 or not color.startswith("#") or any(c not in "0123456789abcdefABCDEF" for c in color[1:])):
            raise ValidationError("Usa un color hexadecimal, por ejemplo #C62828.")
        return color


# ----------------------------------- Roles -----------------------------------
class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(), required=False, label="Permisos",
        widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Role
        fields = ["code", "name", "description", "scope", "permissions", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.code in BASE_ROLE_CODES:
            self.fields["code"].disabled = True  # los 4 roles base no cambian de código

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().lower().replace(" ", "_")
        qs = Role.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ya existe un rol con ese código.")
        return code

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.code in BASE_ROLE_CODES and cleaned.get("is_active") is False:
            raise ValidationError("Los roles base del sistema no se pueden desactivar.")
        return cleaned


# ---------------------------------- Usuarios ----------------------------------
class EmployeeUserForm(forms.ModelForm):
    """Usuario del sistema = auth.User + Employee, guardados en una sola transacción."""
    username = forms.CharField(label="Nombre de usuario", max_length=150)
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo")
    is_active = forms.BooleanField(label="Activo", required=False, initial=True)
    password1 = forms.CharField(label="Contraseña", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirmar contraseña", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = Employee
        fields = ["rut", "phone", "address", "app_role", "delegation", "authorized_delegations"]
        widgets = {"authorized_delegations": forms.CheckboxSelectMultiple}

    field_order = ["username", "first_name", "last_name", "email", "rut", "phone", "address",
                   "app_role", "delegation", "authorized_delegations", "is_active", "password1", "password2"]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        allowed = allowed_delegations(actor, only_active=True)
        self.fields["delegation"].queryset = allowed
        self.fields["authorized_delegations"].queryset = allowed
        self.fields["authorized_delegations"].required = False
        self.fields["app_role"].queryset = Role.objects.filter(is_active=True, code__in=assignable_role_codes(actor))
        self.fields["app_role"].required = True
        self.fields["app_role"].label = "Rol"
        self.fields["delegation"].label = "Delegación principal"
        self.fields["authorized_delegations"].label = "Otras delegaciones autorizadas"
        if self.instance.pk:
            u = self.instance.user
            self.initial.update(username=u.username, first_name=u.first_name, last_name=u.last_name,
                                email=u.email, is_active=u.is_active)
            self.fields["password1"].help_text = "Déjala en blanco para no cambiarla."
        else:
            self.fields["password1"].required = self.fields["password2"].required = True

    def _user_qs(self):
        qs = User.objects.all()
        return qs.exclude(pk=self.instance.user_id) if self.instance.pk else qs

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        if self._user_qs().filter(username__iexact=value).exists():
            raise ValidationError("Ese nombre de usuario ya está en uso.")
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if self._user_qs().filter(email__iexact=value).exists():
            raise ValidationError("Ese correo ya está registrado.")
        return value

    def clean_rut(self):
        rut = self.cleaned_data["rut"].strip().upper()
        qs = Employee.objects.filter(rut__iexact=rut)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ese RUT ya está registrado.")
        return rut

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 or p2 or not self.instance.pk:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            elif p1:
                probe = User(username=cleaned.get("username", ""), email=cleaned.get("email", ""),
                            first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""))
                try:
                    validate_password(p1, probe)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        # No dejar al actor sin acceso por error
        if self.instance.pk and self.instance.user_id == self.actor.pk and not cleaned.get("is_active"):
            self.add_error("is_active", "No puedes desactivar tu propia cuenta.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        cd = self.cleaned_data
        emp = super().save(commit=False)
        user = emp.user if emp.pk else User()
        user.username, user.email = cd["username"], cd["email"]
        user.first_name, user.last_name = cd["first_name"], cd["last_name"]
        user.is_active = cd["is_active"]
        if cd.get("password1"):
            user.set_password(cd["password1"])
        elif not user.pk:
            user.set_unusable_password()
        user.save()
        emp.user = user
        role = cd["app_role"]
        emp.role = "usuario" if role.code == FUNCIONARIO else "jefatura"  # compatibilidad con el Admin
        emp.save()
        authorized = cd.get("authorized_delegations") or []
        if role.scope == Role.SCOPE_OWN:
            authorized = []
        emp.authorized_delegations.set(authorized)
        return emp
