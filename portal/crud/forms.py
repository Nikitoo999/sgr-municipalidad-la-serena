"""Formularios del CRUD (Parte 4: Delegaciones)."""

from django import forms
from django.core.validators import RegexValidator

from sgr_core.models import Delegation

HEX_COLOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="El color debe tener el formato #RRGGBB, por ejemplo #920000.",
)


class DelegationForm(forms.ModelForm):
    """Delegación: código (único, mayúsculas), nombre (único), comuna,
    dirección, color hex y estado."""

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
            "code": "Código interno corto, por ejemplo DEL08. Se guarda en mayúsculas.",
            "name": "Nombre visible de la delegación. Debe ser único.",
            "commune": "Comuna de la delegación.",
            "address": "Dirección o referencia de la oficina (opcional).",
            "color": "Color de apoyo de la insignia. Nunca identifica la delegación por sí solo: siempre va con el código y el nombre.",
            "status": "Las delegaciones inactivas no aparecen en los selectores de atención.",
        }
        widgets = {
            "code": forms.TextInput(
                attrs={"class": "in", "maxlength": 8, "placeholder": "DEL08",
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

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not code:
            raise forms.ValidationError("Ingresa el código de la delegación.")
        exists = Delegation.objects.filter(code=code)
        if self.instance and self.instance.pk:
            exists = exists.exclude(pk=self.instance.pk)
        if exists.exists():
            raise forms.ValidationError(
                "Ya existe una delegación con este código."
            )
        return code

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
