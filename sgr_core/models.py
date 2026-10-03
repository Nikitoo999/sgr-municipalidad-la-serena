from django.db import models

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última modificación")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de eliminación")

    class Meta:
        abstract = True

class Delegation(BaseModel):
    name = models.CharField(max_length=50, verbose_name="Nombre de Delegación")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    color = models.CharField(max_length=7, blank=True, default="", help_text="Código hex, ej: #E63946", verbose_name="Color distintivo")

    class Meta:
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"
        db_table = "delegacion"

    def __str__(self):
        return self.name

class Period(BaseModel):
    name = models.CharField(max_length=30, verbose_name="Nombre del Período")
    start_date = models.DateField(verbose_name="Fecha Inicio")
    end_date = models.DateField(verbose_name="Fecha Fin")
    quarter = models.IntegerField(choices=[(1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')], verbose_name="Trimestre")
    status = models.CharField(max_length=15, default="En curso", choices=[("En curso", "En curso"), ("Cerrado", "Cerrado")], verbose_name="Estado")

    class Meta:
        verbose_name = "Período de Medición"
        verbose_name_plural = "Períodos de Medición"
        db_table = "periodo"

    def __str__(self):
        return f"{self.name} (T{self.quarter})"

class InstitutionalGoal(BaseModel):
    name = models.CharField(max_length=100, verbose_name="Meta Institucional")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Ponderación (%)")
    period = models.ForeignKey(Period, on_delete=models.RESTRICT, related_name="goals", verbose_name="Período")
    delegation = models.ForeignKey(Delegation, on_delete=models.RESTRICT, related_name="goals", verbose_name="Delegación")

    class Meta:
        verbose_name = "Meta Institucional"
        verbose_name_plural = "Metas Institucionales"
        db_table = "meta"

    def __str__(self):
        return f"{self.name} ({self.weight}%)"

class Achievement(BaseModel):
    goal = models.ForeignKey(InstitutionalGoal, on_delete=models.CASCADE, related_name="achievements", verbose_name="Meta")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Porcentaje Cumplido (%)")

    class Meta:
        verbose_name = "Registro de Cumplimiento"
        verbose_name_plural = "Registros de Cumplimiento"
        db_table = "cumplimiento"

    def __str__(self):
        return f"{self.goal.name}: {self.percentage}%"

class MeasurementItem(BaseModel):
    goal = models.ForeignKey(InstitutionalGoal, on_delete=models.CASCADE, related_name="measurement_items", verbose_name="Meta")
    name = models.CharField(max_length=100, verbose_name="Indicador / Item de Medición")
    unit_of_measure = models.CharField(max_length=50, verbose_name="Unidad de Medida")
    baseline = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Línea Base")
    target_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Valor Objetivo")

    class Meta:
        verbose_name = "Ítem de Medición"
        verbose_name_plural = "Ítems de Medición"
        db_table = "item_medicion"

    def __str__(self):
        return f"{self.name} ({self.unit_of_measure})"