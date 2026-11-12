"""Formularios del CRUD (Parte 4: Delegaciones; Parte 5: Roles y Usuarios)."""

import logging
import secrets

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import RegexValidator
from django.db import transaction

from operaciones import rules as attention_rules
from operaciones.models import Attention, Employee, Neighbor
from portal.validators import normalize_phone, validate_full_name, validate_rut
from sgr_core.models import (
    AttentionSubtype,
    AttentionType,
    Delegation,
    ProjectItem,
    Role,
    RolePermission,
)
from sgr_core.roles import ACTIONS, MODULES

from ..access import (
    ALL_DELEGATIONS,
    allowed_delegations,
    get_active_delegation,
    get_role,
)
from sgr_core.roles import SCOPE_RANKS

User = get_user_model()

logger = logging.getLogger(__name__)

HEX_COLOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="El color debe tener el formato #RRGGBB, por ejemplo #920000.",
)


class CrudModelForm(forms.ModelForm):
    """Base de los formularios del motor.

    Expone ``full_width_fields`` (nombres de campo que ocupan toda la fila del
    formulario) para que la plantilla ``portal/crud/form.html`` no dependa de
    una lista fija de nombres. El valor por defecto conserva el comportamiento
    de la Parte 4 (Delegaciones); cada módulo puede ampliarlo.

    Recibe ``request`` (lo pasa el motor) para que el formulario resuelva
    reglas que dependen del operador: roles ofrecidos, delegaciones que puede
    administrar, su delegación activa, etc.
    """

    full_width_fields = ('description', 'address')

    #: Campo con código correlativo automático (Bloque 2A). Al crear no se
    #: muestra (lo asigna ``AutoCodeMixin.save()``); al editar o consultar
    #: queda de solo lectura: un campo ``disabled`` ignora lo que llegue por
    #: POST, así un formulario manipulado no puede cambiar el código.
    auto_code_field = None

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        self._setup_auto_code()

    def _setup_auto_code(self):
        name = self.auto_code_field
        if not name or name not in self.fields:
            return
        if self.instance.pk is None:
            del self.fields[name]
            return
        field = self.fields[name]
        field.disabled = True
        field.required = False
        field.help_text = "Código correlativo asignado por el sistema; no se puede modificar."


class DelegationForm(CrudModelForm):
    """Delegación: código automático (DEL01...), nombre (único), comuna,
    dirección, color hex y estado."""

    auto_code_field = "code"

    class Meta:
        model = Delegation
        fields = ("code", "name", "commune", "address", "color", "status")
        labels = {
            "code": "Código",
            "name": "Nombre de la delegación",
            "commune": "Comuna",
            "address": "Dirección",
            "color": "Color distintivo",
            "status": "Estado",
        }
        help_texts = {
            "name": "Nombre visible de la delegación. Debe ser único.",
            "commune": "Comuna de la delegación.",
            "address": "Dirección o referencia de la oficina (opcional).",
            "color": "Color de apoyo de la insignia. Nunca identifica la delegación por sí solo: siempre va con el código y el nombre.",
            "status": "Las delegaciones inactivas no aparecen en los selectores de atención.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "in", "maxlength": 8,
                       "aria-describedby": "id_code-help id_code-e"},
            ),
            "name": forms.TextInput(
                attrs={"class": "in", "maxlength": 50, "placeholder": "Centro",
                       "aria-describedby": "id_name-help id_name-e"},
            ),
            "commune": forms.TextInput(
                attrs={"class": "in", "maxlength": 80, "placeholder": "La Serena",
                       "aria-describedby": "id_commune-help id_commune-e"},
            ),
            "address": forms.TextInput(
                attrs={"class": "in", "maxlength": 200, "placeholder": "Calle Ejemplo 123",
                       "aria-describedby": "id_address-help id_address-e"},
            ),
            "color": forms.TextInput(
                attrs={
                    "class": "in",
                    "maxlength": 7,
                    "placeholder": "#920000",
                    "inputmode": "text",
                    "data-color-input": "1",
                    "aria-describedby": "id_color-help id_color-e",
                },
            ),
            "status": forms.Select(
                attrs={"class": "in", "aria-describedby": "id_status-help id_status-e"},
            ),
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Ingresa el nombre de la delegación.")
        exists = Delegation.alive.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise forms.ValidationError(
                "Ya existe una delegación con este nombre."
            )
        return name

    def clean_color(self):
        color = (self.cleaned_data.get("color") or "").strip()
        if color and not color.startswith("#"):
            color = f"#{color}"
        if color:
            HEX_COLOR(color)
        return color


# ============================================================
# Roles (Parte 5): matriz de permisos módulo × acción
# ============================================================

#: Etiquetas en es-cl de módulos y acciones (claves en inglés).
MODULE_LABELS = dict(MODULES)
ACTION_LABELS = dict(ACTIONS)

#: Opciones válidas de la matriz: "modulo.accion" -> "Módulo: Acción".
PERMISSION_CHOICES = [
    (f"{module_key}.{action_key}",
     f"{MODULE_LABELS.get(module_key, module_key)}: {ACTION_LABELS.get(action_key, action_key)}")
    for module_key, _ in MODULES
    for action_key, _ in ACTIONS
]


class PermissionMatrixWidget(forms.CheckboxSelectMultiple):
    """Matriz de permisos módulo × acción como tabla de casillas.

    Cada casilla lleva ``aria-label`` accesible ("Módulo: Acción") y respeta el
    atributo ``disabled`` del widget, que el motor activa en la vista de
    consulta (``portal/crud/views.py`` deshabilita todos los campos).
    """

    template_name = "portal/crud/permission_matrix.html"

    def __init__(self, *args, **kwargs):
        self.modules = tuple(kwargs.pop("modules", MODULES))
        self.actions = tuple(kwargs.pop("actions", ACTIONS))
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selected = {str(item) for item in (value or [])}
        context["widget"]["matrix"] = [
            {
                "key": module_key,
                "label": MODULE_LABELS.get(module_key, module_key),
                "actions": [
                    {
                        "key": action_key,
                        "label": ACTION_LABELS.get(action_key, action_key),
                        "checked": f"{module_key}.{action_key}" in selected,
                    }
                    for action_key, _ in self.actions
                ],
            }
            for module_key, _ in self.modules
        ]
        context["widget"]["disabled"] = bool(attrs.get("disabled"))
        return context


class RoleForm(CrudModelForm):
    """Rol: código automático (ROL01...), nombre, descripción, alcance, estado
    y la matriz de permisos módulo × acción.

    Reglas validadas en el servidor:
    - un módulo con cualquier acción create/edit/delete/export exige también "Ver";
    - al menos un módulo habilitado;
    - el rol del sistema (``is_system``) solo se puede consultar;
    - un rol con usuarios asignados no se puede desactivar.
    """

    full_width_fields = ('description', 'permissions')
    auto_code_field = "code"

    #: Matriz como lista de valores "modulo.accion".
    permissions = forms.MultipleChoiceField(
        label="Permisos por módulo",
        required=False,
        choices=PERMISSION_CHOICES,
        widget=PermissionMatrixWidget(),
    )

    class Meta:
        model = Role
        fields = ("code", "name", "description", "scope", "status")
        labels = {
            "code": "Código",
            "name": "Nombre del rol",
            "description": "Descripción",
            "scope": "Alcance de datos",
            "status": "Estado",
        }
        help_texts = {
            "name": "Nombre visible del rol. Debe ser único.",
            "description": "Explica qué hace este perfil (opcional).",
            "scope": "Define qué delegaciones puede ver el rol.",
            "status": "Un rol inactivo no permite el acceso al sistema.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "in", "maxlength": 8,
                       "aria-describedby": "id_code-help id_code-e"},
            ),
            "name": forms.TextInput(
                attrs={"class": "in", "maxlength": 50, "placeholder": "Coordinador",
                       "aria-describedby": "id_name-help id_name-e"},
            ),
            "description": forms.Textarea(
                attrs={"class": "in", "rows": 3, "maxlength": 200,
                       "aria-describedby": "id_description-help id_description-e"},
            ),
            "scope": forms.Select(
                attrs={"class": "in", "aria-describedby": "id_scope-help id_scope-e"},
            ),
            "status": forms.Select(
                attrs={"class": "in", "aria-describedby": "id_status-help id_status-e"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance is not None and instance.pk:
            self.fields["permissions"].initial = [
                f"{module}.{action}"
                for module, action in RolePermission.objects.filter(
                    role=instance
                ).values_list("module", "action")
            ]

    # ---------------------------------------------------------------
    # Validaciones del servidor
    # ---------------------------------------------------------------

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Ingresa el nombre del rol.")
        exists = Role.alive.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise forms.ValidationError("Ya existe un rol con este nombre.")
        return name

    def clean_permissions(self):
        """Matriz: al menos un módulo y "Ver" obligatorio donde haya acciones."""
        pairs = set(self.cleaned_data.get("permissions") or [])
        by_module = {}
        for pair in pairs:
            module, _, action = pair.partition(".")
            by_module.setdefault(module, set()).add(action)
        if not by_module:
            raise forms.ValidationError("Habilita al menos un módulo.")
        for module, actions in by_module.items():
            if actions and "view" not in actions:
                raise forms.ValidationError(
                    "Cada módulo con acciones debe incluir «Ver»."
                )
        return sorted(pairs)

    def clean(self):
        cleaned = super().clean()
        instance = getattr(self, "instance", None)
        if instance is None or not instance.pk:
            return cleaned
        # El rol del sistema solo se puede consultar (ni editar ni eliminar).
        # Error general: form.html ya renderiza form.non_field_errors.
        if instance.is_system:
            raise forms.ValidationError(
                f"El rol {instance.name} es el perfil base del sistema: solo se "
                f"puede consultar, no admite cambios."
            )
        # Un rol con usuarios asignados no se puede desactivar.
        if cleaned.get("status") == "Inactivo" and instance.status == "Activo":
            users = instance.employees.count()
            if users:
                raise forms.ValidationError(
                    f"No se puede desactivar el rol {instance.name} porque tiene "
                    f"{users} usuario(s) asignado(s). Reasínalos a otro perfil "
                    f"antes de desactivarlo."
                )
        return cleaned

    def save(self, commit=True):
        """Guarda el rol y sincroniza la matriz en una sola transacción."""
        with transaction.atomic():
            role = super().save(commit=commit)
            wanted = {
                tuple(pair.split(".", 1))
                for pair in self.cleaned_data.get("permissions") or []
                if "." in pair
            }
            existing = set(
                RolePermission.objects.filter(role=role).values_list(
                    "module", "action"
                )
            )
            for module, action in sorted(wanted - existing):
                RolePermission.objects.get_or_create(
                    role=role, module=module, action=action,
                )
            for module, action in sorted(existing - wanted):
                RolePermission.objects.filter(
                    role=role, module=module, action=action,
                ).delete()
        return role


# ============================================================
# Usuarios (Parte 5, Etapa 2): User + Employee en una transacción
# ============================================================

#: Alcances que usan UNA sola delegación (la base).
SINGLE_DELEGATION_SCOPES = ("own_delegation", "own_records")


class UserForm(CrudModelForm):
    """Formulario único que crea o edita ``User`` + ``Employee``.

    Toda la autorización se valida en el servidor con ``self.request`` (el
    operador): los roles ofrecidos, las delegaciones que puede administrar y la
    delegación base cuando el rol tiene alcance total. El JavaScript solo ayuda
    a mostrar el control adecuado: un POST manipulado se rechaza aquí.
    """

    full_width_fields = ("address", "delegations")

    # ---- Campos de User ---------------------------------------------
    first_name = forms.CharField(
        label="Nombre", max_length=150,
        widget=forms.TextInput(attrs={"class": "in", "maxlength": 150}),
    )
    last_name = forms.CharField(
        label="Apellido", max_length=150,
        widget=forms.TextInput(attrs={"class": "in", "maxlength": 150}),
    )
    email = forms.EmailField(
        label="Correo electrónico", max_length=254,
        widget=forms.EmailInput(attrs={"class": "in", "maxlength": 254}),
    )
    status = forms.ChoiceField(
        label="Estado",
        choices=(("Activo", "Activo"), ("Inactivo", "Inactivo")),
        widget=forms.Select(attrs={"class": "in"}),
    )
    # ---- Contraseña: solo al crear ----------------------------------
    password1 = forms.CharField(
        label="Contraseña inicial", required=False, strip=False,
        help_text="Si la dejas en blanco, se generará automáticamente una contraseña provisoria segura y se enviará por correo al funcionario.",
        widget=forms.PasswordInput(
            attrs={"class": "in", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmar contraseña", required=False, strip=False,
        widget=forms.PasswordInput(
            attrs={"class": "in", "autocomplete": "new-password"}),
    )
    # ---- Delegaciones (base y/o autorizadas) ------------------------
    delegations = forms.MultipleChoiceField(label="Delegaciones", required=False)

    class Meta:
        model = Employee
        fields = ("rut", "phone", "address", "role")
        labels = {
            "rut": "RUT",
            "phone": "Teléfono",
            "address": "Dirección",
            "role": "Rol",
        }
        help_texts = {
            "rut": "RUT del funcionario, por ejemplo 12.345.678-5. Debe ser único.",
            "phone": "Teléfono de contacto (opcional).",
            "address": "Dirección o referencia (opcional).",
            "role": "Solo se pueden asignar roles de menor alcance que el tuyo.",
        }
        widgets = {
            "rut": forms.TextInput(
                attrs={"class": "in", "maxlength": 12, "placeholder": "12.345.678-5",
                       "aria-describedby": "id_rut-help id_rut-e"},
            ),
            "phone": forms.TextInput(
                attrs={"class": "in", "maxlength": 20,
                       "placeholder": "+56 9 0000 0000",
                       "aria-describedby": "id_phone-help id_phone-e"},
            ),
            "address": forms.TextInput(
                attrs={"class": "in", "maxlength": 255,
                       "aria-describedby": "id_address-help id_address-e"},
            ),
            "role": forms.Select(
                attrs={"class": "in", "id": "id_role",
                       "aria-describedby": "id_role-help id_role-e"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.operator = getattr(self.request, "user", None)
        employee = getattr(self, "instance", None)
        self.editing = employee is not None and employee.pk is not None

        # Roles ofrecidos: rango menor al del operador, nunca is_system, y
        # activos (al editar se admite el rol actual aunque esté inactivo).
        # ``role`` es un ModelChoiceField: el queryset se deja amplio para que
        # ``clean_role`` pueda emitir el mensaje específico cuando el rol queda
        # fuera de alcance; las opciones visibles se limitan en ``choices``.
        self.assignable_roles = self._assignable_roles()
        self.fields["role"].queryset = Role.objects.all()
        self.fields["role"].choices = [("", "---------")] + [
            (role.pk, str(role)) for role in self.assignable_roles
        ]
        # Delegaciones que el operador puede administrar.
        self.administrable = self._administrable_delegations()
        # Al editar, las delegaciones actuales siempre se ofrecen (para que la
        # vista de consulta, que no recibe request, las muestre marcadas).
        self.current_delegations = (
            list(employee.authorized_delegations.all())
            if self.editing else []
        )
        if self.editing and employee.delegation_id:
            if employee.delegation not in self.current_delegations:
                self.current_delegations.insert(0, employee.delegation)
        offered = self.administrable + [
            d for d in self.current_delegations
            if d not in self.administrable
        ]
        # El widget se asigna ANTES de las choices: la propiedad 
        # ``choices`` del campo propaga su valor al widget actual, así que si
        # se reemplaza el widget después, el nuevo quedaría sin opciones (bug).
        self.fields["delegations"].widget = forms.CheckboxSelectMultiple(
            attrs={"id": "id_delegations"},
        )
        self.fields["delegations"].choices = [
            (str(d.pk), f"{d.code} | Delegación {d.name}") for d in offered
        ]
        self.fields["delegations"].label = self._delegations_label()

        if self.editing:
            user = employee.user
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email
            self.fields["status"].initial = "Activo" if user.is_active else "Inactivo"
            self.fields["delegations"].initial = [
                str(d.pk) for d in self.current_delegations
            ]
            # Al editar no se toca la clave (y por tanto tampoco el username).
            del self.fields["password1"]
            del self.fields["password2"]

    # ---------------------------------------------------------------
    # Reglas resueltas con el operador (request)
    # ---------------------------------------------------------------

    def _assignable_roles(self):
        """Roles que el operador puede asignar (rango menor, sin is_system)."""
        employee = getattr(self, "instance", None)
        if self.operator is None or not self.operator.is_authenticated:
            # Sin operador (vista de consulta): solo el rol ya asignado.
            if self.editing and employee.role_id:
                return [employee.role]
            return []
        roles = list(Role.alive.filter(is_system=False))
        # El rol actual siempre se ofrece al editar (aunque esté inactivo), para
        # que la consulta y la edición lo muestren seleccionado.
        if self.editing and employee.role_id and employee.role not in roles:
            roles.insert(0, employee.role)
        if self.operator.is_superuser:
            return roles
        operator_role = get_role(self.operator)
        if operator_role is None:
            return []
        return [
            role for role in roles
            if SCOPE_RANKS.get(role.scope, 0) < operator_role.rank
        ]

    def _administrable_delegations(self):
        """Delegaciones que el operador puede administrar."""
        if self.operator is None or not self.operator.is_authenticated:
            return []
        return list(allowed_delegations(self.operator))

    def _selected_role(self):
        """Rol elegido en el POST (o el actual al editar)."""
        role_id = self.data.get("role")
        if role_id:
            try:
                return Role.objects.filter(pk=role_id).first()
            except (TypeError, ValueError):
                return None
        employee = getattr(self, "instance", None)
        return employee.role if self.editing else None

    def _delegations_label(self):
        """Etiqueta del campo de delegaciones según el alcance del rol."""
        role = self._selected_role()
        if role is not None and role.scope == "all":
            return "Delegaciones (no aplica: el rol abarca todas)"
        return "Delegaciones"

    @property
    def role_scopes_json(self):
        """JSON ``{pk: scope}`` de los roles ofrecidos (para el JavaScript).

        La interfaz solo muestra u oculta el bloque de delegaciones según el
        alcance; la validación real de "qué delegaciones puede administrar"
        siempre se hace en el servidor.
        """
        import json

        return json.dumps(
            {str(role.pk): role.scope for role in self.assignable_roles}
        )

    # ---------------------------------------------------------------
    # Validaciones del servidor
    # ---------------------------------------------------------------

    def clean_rut(self):
        rut = validate_rut(self.cleaned_data.get("rut"))
        exists = Employee.objects.filter(rut=rut)
        if self.editing:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise forms.ValidationError("Ya existe un funcionario con este RUT.")
        return rut

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            raise forms.ValidationError("Ingresa el correo electrónico.")
        exists = User.objects.filter(email__iexact=email)
        if self.editing:
            exists = exists.exclude(pk=self.instance.user_id)
        if exists.exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email

    def clean_role(self):
        """El rol debe ser asignable por el operador y nunca is_system."""
        role = self.cleaned_data.get("role")
        if role is None:
            raise forms.ValidationError("Selecciona un rol.")
        if role.is_system:
            raise forms.ValidationError(
                "El perfil del sistema no se puede asignar desde el mantenedor."
            )
        if role not in self.assignable_roles:
            raise forms.ValidationError(
                "No puedes asignar un rol de alcance igual o superior al tuyo."
            )
        # Nadie cambia su propio rol.
        if (
            self.editing
            and self.operator is not None
            and self.instance.user_id == getattr(self.operator, "pk", None)
        ):
            if role.pk != self.instance.role_id:
                raise forms.ValidationError("No puedes cambiar tu propio rol.")
        return role

    def clean_delegations(self):
        """Delegaciones válidas para el operador y coherentes con el alcance."""
        role = self._selected_role()
        chosen = list(self.cleaned_data.get("delegations") or [])
        if role is None:
            return chosen

        # Solo delegaciones que el operador puede administrar.
        administrable = {str(d.pk) for d in self.administrable}
        outside = [pk for pk in chosen if pk not in administrable]
        if outside:
            raise forms.ValidationError(
                "Hay delegaciones seleccionadas que no puedes administrar."
            )

        if role.scope == "all":
            # El rol abarca todas las delegaciones: no se asignan autorizadas.
            return []
        if role.scope == "authorized":
            if not chosen:
                raise forms.ValidationError(
                    "El rol «Delegaciones autorizadas» exige al menos una delegación."
                )
        else:  # own_delegation / own_records: exactamente una.
            if len(chosen) != 1:
                raise forms.ValidationError(
                    "El alcance de este rol exige exactamente una delegación."
                )
        return chosen

    def clean(self):
        cleaned = super().clean()
        if self.editing:
            return cleaned
        # Contraseña inicial y confirmación solo al crear.
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if not password1 and not password2:
            # Sin clave escrita: se genera una provisoria segura y se envía por correo.
            cleaned["generated_password"] = f"Sgr{secrets.token_urlsafe(6)}9!"
        elif not password1:
            self.add_error("password1", "Ingresa la contraseña inicial.")
        elif password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        else:
            try:
                validate_password(password1, self._password_user())
            except DjangoValidationError as exc:
                self.add_error("password1", " ".join(exc.messages))
        return cleaned

    def _password_user(self):
        """Usuario (posible) para los validadores de contraseña de Django."""
        email = self.data.get("email") or ""
        username = email.strip().lower() or "nuevo.usuario"
        return User(username=username, email=email.strip())

    # ---------------------------------------------------------------
    # Guardado (User + Employee en una sola transacción)
    # ---------------------------------------------------------------

    def save(self, commit=True):
        with transaction.atomic():
            user = self._save_user()
            employee = super().save(commit=False)
            employee.user = user

            role = self.cleaned_data.get("role")
            chosen = list(self.cleaned_data.get("delegations") or [])
            employee.role = role

            if role.scope == "all":
                # Employee.delegation es obligatoria: se guarda como base la
                # delegación activa del operador (o la primera activa por código
                # si su contexto es "Todas"). authorized_delegations queda vacío.
                employee.delegation = self._base_delegation()
            else:
                base = self._delegation_by_pk(chosen[0])
                employee.delegation = base
            if not self.editing:
                employee.must_change_password = True
            employee.save()

            if role.scope == "authorized":
                # Incluye la base más las demás autorizadas elegidas.
                pks = list(dict.fromkeys(chosen))
                if str(employee.delegation_id) not in pks:
                    pks.insert(0, str(employee.delegation_id))
                employee.authorized_delegations.set(
                    [self._delegation_by_pk(pk) for pk in pks]
                )
            else:
                employee.authorized_delegations.clear()

            user.is_active = self.cleaned_data.get("status") == "Activo"
            user.save(update_fields=["is_active"])

        if not self.editing:
            self._send_provisional_credentials(user)

        return employee

    def _save_user(self):
        """Crea la cuenta (username = correo) o actualiza nombre y correo."""
        email = (self.cleaned_data.get("email") or "").strip()
        first_name = (self.cleaned_data.get("first_name") or "").strip()
        last_name = (self.cleaned_data.get("last_name") or "").strip()

        if self.editing:
            user = self.instance.user
            # Al editar NO se cambia el username.
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.save(update_fields=["email", "first_name", "last_name"])
            return user

        password = self.cleaned_data.get("password1") or self.cleaned_data.get("generated_password")
        user = User.objects.create_user(
            username=email.lower(), email=email,
            first_name=first_name, last_name=last_name,
        )
        user.set_password(password)
        user.save(update_fields=["password"])
        return user

    def _send_provisional_credentials(self, user):
        """Envía por correo la contraseña provisoria del usuario nuevo."""
        password = self.cleaned_data.get("password1") or self.cleaned_data.get("generated_password")
        subject = 'Credenciales de acceso - Sistema Municipal'
        message = (
            f'Se ha creado tu cuenta en el Sistema de Gestión de Reclamos (SGR).\n\n'
            f'Usuario: {user.email}\n'
            f'Contraseña provisoria: {password}\n\n'
            f'Deberás cambiarla en tu primer ingreso.\n'
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        except Exception as exc:
            logger.error(f'Error enviando contraseña provisoria a {user.email}: {exc}')

    def _delegation_by_pk(self, pk):
        """Delegación administrable por pk (o la primera como respaldo)."""
        for delegation in self.administrable:
            if str(delegation.pk) == str(pk):
                return delegation
        return self.administrable[0]

    def _base_delegation(self):
        """Delegación base cuando el rol abarca todas las delegaciones.

        Es la delegación activa del operador; si su contexto es «Todas», la
        primera activa por código.
        """
        active = get_active_delegation(self.request)
        if active is not None and active != ALL_DELEGATIONS:
            return active
        for delegation in self.administrable:
            if delegation.status == "Activa":
                return delegation
        if self.administrable:
            return sorted(self.administrable, key=lambda d: d.code)[0]
        raise forms.ValidationError(
            "No hay delegaciones disponibles para asignar la delegación base."
        )


# ============================================================
# Parte 6: Ítems, Tipos de atención y Sub atenciones (catálogos)
# ============================================================


class ProjectItemForm(CrudModelForm):
    """Ítem de proyecto: código automático (ITM001...), nombre, descripción y estado."""

    auto_code_field = "code"

    class Meta:
        model = ProjectItem
        fields = ("code", "name", "description", "status")
        labels = {
            "code": "Código",
            "name": "Nombre del ítem",
            "description": "Descripción",
            "status": "Estado",
        }
        help_texts = {
            "name": "Nombre visible del ítem.",
            "description": "Explica qué mide este ítem (opcional).",
            "status": "Un ítem inactivo no aparece en los formularios nuevos.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "in", "maxlength": 8,
                       "aria-describedby": "id_code-help id_code-e"},
            ),
            "name": forms.TextInput(
                attrs={"class": "in", "maxlength": 100,
                       "placeholder": "Operativos en terreno",
                       "aria-describedby": "id_name-help id_name-e"},
            ),
            "description": forms.Textarea(
                attrs={"class": "in", "rows": 3,
                       "aria-describedby": "id_description-help id_description-e"},
            ),
            "status": forms.Select(
                attrs={"class": "in", "aria-describedby": "id_status-help id_status-e"},
            ),
        }


class AttentionTypeForm(CrudModelForm):
    """Tipo de atención: código automático (TAT01...), nombre, descripción y estado."""

    auto_code_field = "code"

    class Meta:
        model = AttentionType
        fields = ("code", "name", "description", "status")
        labels = {
            "code": "Código",
            "name": "Nombre del tipo",
            "description": "Descripción",
            "status": "Estado",
        }
        help_texts = {
            "name": "Nombre visible del tipo de atención.",
            "description": "Explica qué agrupa este tipo (opcional).",
            "status": "Un tipo inactivo no aparece al crear sub atenciones nuevas.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "in", "maxlength": 8,
                       "aria-describedby": "id_code-help id_code-e"},
            ),
            "name": forms.TextInput(
                attrs={"class": "in", "maxlength": 100, "placeholder": "Social",
                       "aria-describedby": "id_name-help id_name-e"},
            ),
            "description": forms.Textarea(
                attrs={"class": "in", "rows": 3,
                       "aria-describedby": "id_description-help id_description-e"},
            ),
            "status": forms.Select(
                attrs={"class": "in", "aria-describedby": "id_status-help id_status-e"},
            ),
        }


class AttentionSubtypeForm(CrudModelForm):
    """Sub atención: código automático (SAT001...), nombre, tipo asociado y estado.

    Solo se ofrecen tipos Activos; al editar se conserva el tipo actual aunque
    esté inactivo, para que la consulta/edición lo muestre seleccionado.
    """

    auto_code_field = "code"

    class Meta:
        model = AttentionSubtype
        fields = ("code", "name", "attention_type", "status")
        labels = {
            "code": "Código",
            "name": "Nombre de la sub atención",
            "attention_type": "Tipo de atención",
            "status": "Estado",
        }
        help_texts = {
            "name": "Nombre visible de la sub atención.",
            "attention_type": "Solo se ofrecen tipos activos.",
            "status": "Una sub atención inactiva no aparece en los formularios nuevos.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "in", "maxlength": 8,
                       "aria-describedby": "id_code-help id_code-e"},
            ),
            "name": forms.TextInput(
                attrs={"class": "in", "maxlength": 100, "placeholder": "Ayuda social",
                       "aria-describedby": "id_name-help id_name-e"},
            ),
            "attention_type": forms.Select(
                attrs={"class": "in",
                       "aria-describedby": "id_attention_type-help id_attention_type-e"},
            ),
            "status": forms.Select(
                attrs={"class": "in", "aria-describedby": "id_status-help id_status-e"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo tipos Activos; al editar se conserva el actual aunque esté inactivo.
        qs = AttentionType.alive.filter(status="Activo").order_by("code")
        if self.instance and self.instance.pk and self.instance.attention_type_id:
            current = self.instance.attention_type
            if current.status != "Activo":
                qs = AttentionType.objects.filter(
                    pk__in=list(qs.values_list("pk", flat=True)) + [current.pk]
                ).order_by("code")
        self.fields["attention_type"].queryset = qs


class AttentionForm(CrudModelForm):
    """Ingreso / edición de una atención ciudadana (Parte 7 + Bloque 2B).

    Reglas del diseño "Ingreso de atención":

    - Vecino o solicitante (2.5): RUT (validado con dígito verificador),
      nombre completo y teléfono son obligatorios al ingresar. Si el RUT ya
      existe se reutiliza el vecino y se actualizan su nombre y teléfono; si
      no, se registra al guardar. Queda bloqueado al editar.
    - Delegación: delegado/funcionario la tienen fija por perfil; coordinador y
      superadmin eligen entre las permitidas (la activa preseleccionada). En
      edición nadie la cambia.
    - Tipo y sub atención: solo activos; la sub debe pertenecer al tipo y ambos
      activos. El estado solo se edita al editar (al crear queda "Ingresada").
    - Descripción: entre 10 y 500 caracteres.
    - "Requiere visita a terreno" (2.5): casilla opcional.
    - "Sin resolver" (2.6): dar de baja exige un motivo (10 a 500 caracteres).
    - Tope diario (2.7): máximo 7 ingresos por funcionario y día.
    - Cierre semanal (2.7): no se ingresa en una semana cerrada de la
      delegación ni se edita una atención de una semana cerrada.

    Las reglas de negocio viven en ``operaciones.rules``.
    """

    full_width_fields = ("description", "unresolved_reason")

    neighbor_rut = forms.CharField(
        label="RUT del vecino", max_length=12,
        error_messages={"required": "Ingresa el RUT del vecino."},
        help_text="Con o sin puntos, por ejemplo 12.345.678-5.",
        widget=forms.TextInput(attrs={
            "class": "in", "maxlength": 12, "placeholder": "12.345.678-5",
            "autocomplete": "off", "aria-describedby": "id_neighbor_rut-help id_neighbor_rut-e",
        }),
    )
    neighbor_name = forms.CharField(
        label="Nombre completo", max_length=150,
        error_messages={"required": "Ingresa el nombre completo del vecino."},
        help_text="Nombre y apellido(s).",
        widget=forms.TextInput(attrs={
            "class": "in", "maxlength": 150, "placeholder": "María González Rojas",
            "autocomplete": "off", "aria-describedby": "id_neighbor_name-help id_neighbor_name-e",
        }),
    )
    neighbor_phone = forms.CharField(
        label="Teléfono", max_length=20,
        error_messages={"required": "Ingresa el teléfono de contacto del vecino."},
        help_text="9 dígitos, con o sin +56. Ej.: +56 9 1234 5678.",
        widget=forms.TextInput(attrs={
            "class": "in", "maxlength": 20, "placeholder": "+56 9 1234 5678",
            "inputmode": "tel", "autocomplete": "off",
            "aria-describedby": "id_neighbor_phone-help id_neighbor_phone-e",
        }),
    )

    class Meta:
        model = Attention
        fields = (
            "delegation", "attention_type", "attention_subtype", "description",
            "requires_visit", "status", "unresolved_reason",
            "evidence_image", "attachment",
        )
        labels = {
            "delegation": "Delegación de atención",
            "attention_type": "Tipo de Atención",
            "attention_subtype": "Sub Atención",
            "description": "Descripción de la atención",
            "requires_visit": "Requiere visita a terreno",
            "status": "Estado",
            "unresolved_reason": "Motivo de baja (Sin resolver)",
        }
        widgets = {
            "delegation": forms.Select(attrs={"class": "in"}),
            "attention_type": forms.Select(attrs={"class": "in"}),
            "attention_subtype": forms.Select(attrs={"class": "in"}),
            "description": forms.Textarea(
                attrs={
                    "class": "in", "rows": 4, "maxlength": 500,
                    "placeholder": "Describa la solicitud y los antecedentes necesarios.",
                },
            ),
            "requires_visit": forms.CheckboxInput(attrs={"class": "chk"}),
            "status": forms.Select(attrs={"class": "in"}),
            "unresolved_reason": forms.Textarea(
                attrs={
                    "class": "in", "rows": 3, "maxlength": 500,
                    "placeholder": "Explica por qué la atención se da de baja sin resolver.",
                },
            ),
            "evidence_image": forms.FileInput(
                attrs={"class": "in", "accept": ".jpg,.jpeg,.png"},
            ),
            "attachment": forms.FileInput(
                attrs={"class": "in", "accept": ".pdf,.jpg,.jpeg,.png,.webp"},
            ),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, request=request, **kwargs)
        editing = self.instance.pk is not None
        self.editing = editing
        role = get_role(request.user) if request is not None else None

        if editing:
            # Vecino bloqueado al editar: sus datos se muestran como texto.
            for name in ("neighbor_rut", "neighbor_name", "neighbor_phone"):
                self.fields.pop(name, None)
        else:
            # Estado y motivo de baja solo al editar (al crear queda "Ingresada").
            self.fields.pop("status", None)
            self.fields.pop("unresolved_reason", None)

        # Delegación: fija por perfil (delegado/funcionario) o selector permitido.
        self.fixed_delegation = None
        if role is not None and role.scope in ("own_delegation", "own_records"):
            employee = getattr(request.user, "employee", None)
            self.fixed_delegation = employee.delegation if employee else None
        if editing or self.fixed_delegation is not None:
            self.fields.pop("delegation", None)
        else:
            self.fields["delegation"].queryset = self._allowed_delegations(request)
            active = get_active_delegation(request)
            if active is not None and active != ALL_DELEGATIONS:
                self.fields["delegation"].initial = active.pk

        # Tipos y sub atenciones: solo activos (+ el actual al editar).
        type_qs = AttentionType.alive.filter(status="Activo").order_by("code")
        subtype_qs = AttentionSubtype.alive.filter(status="Activo").order_by("code")
        if editing:
            type_qs = self._with_current(type_qs, self.instance.attention_type_id)
            subtype_qs = self._with_current(subtype_qs, self.instance.attention_subtype_id)
        self.fields["attention_type"].queryset = type_qs
        self.fields["attention_subtype"].queryset = subtype_qs

        # Mensajes específicos en vez del genérico "Este campo es obligatorio."
        required = {
            "delegation": "Selecciona la delegación de atención.",
            "attention_type": "Selecciona el tipo de atención.",
            "attention_subtype": "Selecciona la sub atención.",
        }
        for name, message in required.items():
            if name in self.fields:
                self.fields[name].error_messages["required"] = message

    @staticmethod
    def _with_current(qs, current_pk):
        """Añade el registro actual aunque esté inactivo (para edición)."""
        if not current_pk:
            return qs
        return qs.model.alive.filter(
            pk__in=list(qs.values_list("pk", flat=True)) + [current_pk]
        ).order_by("code")

    def _allowed_delegations(self, request):
        """Delegaciones Activas que el operador puede gestionar (coordinador/superadmin)."""
        if request is None:
            return Delegation.alive.none()
        pks = [delegation.pk for delegation in allowed_delegations(request.user)]
        return Delegation.alive.filter(status="Activa", pk__in=pks).order_by("code")

    # ---------------------------------------------------------------
    # Datos obligatorios del vecino (2.5)
    # ---------------------------------------------------------------

    def clean_neighbor_rut(self):
        return validate_rut(self.cleaned_data.get("neighbor_rut"))

    def clean_neighbor_name(self):
        return validate_full_name(self.cleaned_data.get("neighbor_name"))

    def clean_neighbor_phone(self):
        return normalize_phone(self.cleaned_data.get("neighbor_phone"))

    def clean(self):
        cleaned = super().clean()
        editing = self.instance.pk is not None

        # Delegación (no se cambia al editar).
        if editing:
            delegation = self.instance.delegation
            if delegation is None or delegation.status != "Activa":
                self.add_error(None, "La delegación de esta atención ya no está activa.")
        elif "delegation" in self.fields:
            delegation = cleaned.get("delegation")
            if delegation is None:
                if "delegation" not in self.errors:
                    self.add_error("delegation", "Selecciona la delegación de atención.")
            elif delegation.status != "Activa":
                self.add_error(
                    "delegation",
                    "No se puede ingresar una atención en una delegación Inactiva.",
                )
        else:
            delegation = self.fixed_delegation
            if delegation is None:
                self.add_error(None, "Tu perfil no tiene una delegación asignada.")
            elif delegation.status != "Activa":
                self.add_error(None, "Tu delegación no está activa, no puedes ingresar atenciones.")

        # Vecino: al editar se conserva el existente.
        if editing:
            if self.instance.neighbor is None:
                self.add_error(None, "La atención no tiene un solicitante asociado.")

        # Tipo y sub atención.
        # (Si el campo ya trae su propio error, no se repite el mensaje.)
        attention_type = cleaned.get("attention_type")
        attention_subtype = cleaned.get("attention_subtype")
        if attention_type is None:
            if "attention_type" not in self.errors:
                self.add_error("attention_type", "Selecciona el tipo de atención.")
        elif attention_type.status != "Activo":
            self.add_error("attention_type", "El tipo de atención no está activo.")
        if attention_subtype is None:
            if "attention_subtype" not in self.errors:
                self.add_error("attention_subtype", "Selecciona la sub atención.")
        elif attention_subtype.status != "Activo":
            self.add_error("attention_subtype", "La sub atención no está activa.")
        elif attention_type is not None and attention_subtype.attention_type_id != attention_type.pk:
            self.add_error("attention_subtype", "La sub atención no pertenece al tipo seleccionado.")

        # Descripción (10 a 500 caracteres).
        description = (cleaned.get("description") or "").strip()
        if len(description) < 10:
            self.add_error("description", "Describe la solicitud con al menos 10 caracteres.")
        elif len(description) > 500:
            self.add_error("description", "La descripción no puede superar los 500 caracteres.")
        else:
            cleaned["description"] = description

        if editing:
            self._clean_editing(cleaned)
        else:
            self._clean_creating(delegation)
        return cleaned

    def _clean_creating(self, delegation):
        """Reglas del ingreso: tope diario y semana abierta (2.7)."""
        user = getattr(self.request, "user", None)
        limit_error = attention_rules.daily_limit_error(user)
        if limit_error:
            self.add_error(None, limit_error)
        if delegation is not None:
            closure = attention_rules.closure_for(delegation.pk, attention_rules.local_day())
            if closure is not None:
                self.add_error(
                    None,
                    f"La semana {attention_rules.week_label(closure.week_start)} está "
                    f"cerrada para {delegation.code} | Delegación {delegation.name}: "
                    "no se pueden ingresar atenciones.",
                )

    def _clean_editing(self, cleaned):
        """Reglas de la edición: semana cerrada y motivo de "Sin resolver"."""
        closure = attention_rules.attention_closure(self.instance)
        if closure is not None:
            self.add_error(
                None,
                f"La semana {attention_rules.week_label(closure.week_start)} está cerrada: "
                f"la atención {self.instance.number} no se puede editar.",
            )
        status = cleaned.get("status")
        reason = " ".join((cleaned.get("unresolved_reason") or "").split())
        if status == Attention.AttentionStatus.UNRESOLVED:
            if len(reason) < 10:
                self.add_error(
                    "unresolved_reason",
                    "Indica el motivo para dar de baja la atención como «Sin resolver» "
                    "(al menos 10 caracteres).",
                )
            elif len(reason) > 500:
                self.add_error("unresolved_reason", "El motivo no puede superar los 500 caracteres.")
            else:
                cleaned["unresolved_reason"] = reason
        elif "unresolved_reason" in self.fields:
            # El motivo solo tiene sentido en "Sin resolver": si se reabre, se limpia.
            cleaned["unresolved_reason"] = ""

    def _resolve_neighbor(self):
        """Vecino del RUT ingresado: se reutiliza (actualizando nombre y
        teléfono) o se registra. Incluye los borrados de forma lógica, porque
        el RUT es único en toda la tabla."""
        rut = self.cleaned_data["neighbor_rut"]
        name = self.cleaned_data["neighbor_name"]
        phone = self.cleaned_data["neighbor_phone"]
        neighbor = Neighbor.objects.filter(identifier=rut).first()
        if neighbor is None:
            return Neighbor.objects.create(identifier=rut, full_name=name, phone=phone)
        changed = []
        for field_name, value in (("full_name", name), ("phone", phone)):
            if getattr(neighbor, field_name) != value:
                setattr(neighbor, field_name, value)
                changed.append(field_name)
        if neighbor.deleted_at is not None:
            neighbor.deleted_at = None
            changed.append("deleted_at")
        if changed:
            neighbor.save(update_fields=changed + ["updated_at"])
        return neighbor

    def save(self, commit=True):
        """Guarda la atención; al crear, registra o actualiza al vecino.

        La vista llama a este método dentro de ``transaction.atomic()``, así
        el vecino y la atención se guardan juntos o no se guarda nada.
        """
        instance = super().save(commit=False)
        if instance.pk is None:
            instance.neighbor = self._resolve_neighbor()
            # Delegación fija por perfil (crear): el formulario no la incluye.
            if "delegation" not in self.fields:
                instance.delegation = self.fixed_delegation
        if commit:
            instance.save()
        return instance


class FollowUpForm(forms.Form):
    """Nueva gestión de seguimiento de una atención (2.6)."""

    description = forms.CharField(
        label="Detalle de la gestión",
        error_messages={"required": "Describe la gestión realizada."},
        widget=forms.Textarea(attrs={"class": "in", "rows": 3, "maxlength": 500}),
    )

    def clean_description(self):
        # El largo se valida después de normalizar los espacios.
        text = " ".join((self.cleaned_data.get("description") or "").split())
        if len(text) < 10:
            raise forms.ValidationError("Describe la gestión con al menos 10 caracteres.")
        if len(text) > 500:
            raise forms.ValidationError("La gestión no puede superar los 500 caracteres.")
        return text
