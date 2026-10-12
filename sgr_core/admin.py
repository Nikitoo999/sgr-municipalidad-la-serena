from decimal import Decimal

from django import forms
from django.contrib import admin
from django.db.models import Count, Sum

from .models import Delegation, Period, InstitutionalGoal, Achievement, MeasurementItem


# ---------- Inlines (vistas anidadas) ----------
class MeasurementItemInline(admin.TabularInline):
    """Ítems de medición, editables dentro de la Meta."""
    model = MeasurementItem
    extra = 0
    fields = ('name', 'unit_of_measure', 'baseline', 'target_value')
    show_change_link = True


class GoalInline(admin.TabularInline):
    """Metas de un período, visibles dentro del Período."""
    model = InstitutionalGoal
    extra = 0
    fields = ('name', 'delegation', 'weight')
    show_change_link = True


# ---------- Admin Pro: validación con clean() ----------
class PeriodForm(forms.ModelForm):
    class Meta:
        model = Period
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError(
                "La fecha de término no puede ser anterior a la fecha de inicio."
            )
        return cleaned_data


class InstitutionalGoalForm(forms.ModelForm):
    """Valida la ponderación: 0-100 y suma máxima 100% por período y delegación."""

    class Meta:
        model = InstitutionalGoal
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        weight = cleaned.get("weight")
        period = cleaned.get("period")
        delegation = cleaned.get("delegation")
        if weight is not None and not (Decimal("0") <= weight <= Decimal("100")):
            self.add_error("weight", "La ponderación debe estar entre 0 y 100.")
        elif weight is not None and period and delegation:
            others = InstitutionalGoal.objects.filter(
                period=period, delegation=delegation
            ).exclude(pk=self.instance.pk)
            total = (others.aggregate(t=Sum("weight"))["t"] or Decimal("0")) + weight
            if total > Decimal("100"):
                self.add_error(
                    "weight",
                    f"Las metas de {delegation.name} en {period.name} sumarían {total}%. "
                    f"El máximo es 100% (disponible: {Decimal('100') - (total - weight)}%).",
                )
        return cleaned


class MeasurementItemForm(forms.ModelForm):
    class Meta:
        model = MeasurementItem
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        for field, label in (("baseline", "La línea base"), ("target_value", "El valor objetivo")):
            value = cleaned.get(field)
            if value is not None and value < 0:
                self.add_error(field, f"{label} no puede ser negativo.")
        goal = cleaned.get("goal")
        name = cleaned.get("name")
        if goal and name:
            dup = MeasurementItem.objects.filter(goal=goal, name__iexact=name.strip()) \
                .exclude(pk=self.instance.pk)
            if dup.exists():
                self.add_error("name", "Esa meta ya tiene un ítem con ese nombre.")
        return cleaned


class AchievementForm(forms.ModelForm):
    class Meta:
        model = Achievement
        fields = "__all__"

    def clean_percentage(self):
        value = self.cleaned_data["percentage"]
        if not (Decimal("0") <= value <= Decimal("100")):
            raise forms.ValidationError("El porcentaje debe estar entre 0 y 100.")
        return value


@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = ('name', 'color', 'created_at', 'updated_at')
    list_editable = ('color',)
    search_fields = ('name',)
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    form = PeriodForm
    list_display = ('name', 'quarter', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'quarter')
    search_fields = ('name',)
    ordering = ('-start_date',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [GoalInline]


@admin.register(InstitutionalGoal)
class InstitutionalGoalAdmin(admin.ModelAdmin):
    form = InstitutionalGoalForm
    list_display = ('name', 'delegation', 'period', 'weight', 'items_count')
    list_filter = ('period', 'delegation')
    search_fields = ('name', 'description', 'delegation__name', 'period__name')
    # list_select_related optimiza la BD al traer las FK de una sola vez
    list_select_related = ('delegation', 'period')
    ordering = ('-period__start_date', 'name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MeasurementItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n_items=Count('measurement_items'))

    @admin.display(description="Ítems", ordering='_n_items')
    def items_count(self, obj):
        return obj._n_items


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    form = AchievementForm
    list_display = ('goal', 'percentage', 'updated_at')
    list_filter = ('goal__delegation',)
    list_select_related = ('goal',)
    ordering = ('-updated_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MeasurementItem)
class MeasurementItemAdmin(admin.ModelAdmin):
    form = MeasurementItemForm
    list_display = ('name', 'goal', 'unit_of_measure', 'baseline', 'target_value')
    list_filter = ('goal__delegation', 'goal__period')
    search_fields = ('name', 'unit_of_measure', 'goal__name')
    list_select_related = ('goal', 'goal__delegation')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')
