from django import forms
from django.contrib import admin

from .models import AttentionSubtype, AttentionType


# ---------- Validaciones (clean) ----------
class AttentionTypeForm(forms.ModelForm):
    class Meta:
        model = AttentionType
        fields = ("name", "description", "is_active")

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        # unique=True distingue mayúsculas en algunos motores: se revisa sin distinguir
        dup = AttentionType.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if dup.exists():
            raise forms.ValidationError("Ya existe un Tipo de Atención con ese nombre.")
        return name


class AttentionSubtypeForm(forms.ModelForm):
    class Meta:
        model = AttentionSubtype
        fields = ("attention_type", "name", "description", "is_active")

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get("attention_type")
        name = cleaned.get("name")
        if name:
            name = " ".join(name.split())
            cleaned["name"] = name
        if tipo and name:
            dup = AttentionSubtype.objects.filter(
                attention_type=tipo, name__iexact=name
            ).exclude(pk=self.instance.pk)
            if dup.exists():
                self.add_error("name", "Ese tipo de atención ya tiene una sub atención con ese nombre.")
        return cleaned


# ---------- Inline ----------
class AttentionSubtypeInline(admin.TabularInline):
    """Sub atenciones dentro del Tipo de Atención."""
    model = AttentionSubtype
    form = AttentionSubtypeForm
    extra = 0
    fields = ("name", "description", "is_active")
    show_change_link = True


# ---------- Admins ----------
@admin.register(AttentionType)
class AttentionTypeAdmin(admin.ModelAdmin):
    form = AttentionTypeForm
    list_display = ("name", "is_active", "subtypes_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [AttentionSubtypeInline]

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(_n_sub=Count("subtypes"))

    @admin.display(description="Sub atenciones", ordering="_n_sub")
    def subtypes_count(self, obj):
        return obj._n_sub


@admin.register(AttentionSubtype)
class AttentionSubtypeAdmin(admin.ModelAdmin):
    form = AttentionSubtypeForm
    list_display = ("name", "attention_type", "is_active", "created_at")
    list_filter = ("attention_type", "is_active")
    search_fields = ("name", "description", "attention_type__name")
    list_select_related = ("attention_type",)
    ordering = ("attention_type__name", "name")
    readonly_fields = ("created_at", "updated_at")
