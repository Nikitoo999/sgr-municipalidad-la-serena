from django.db import models
from rrhh.models import Delegacion

class Periodo(models.Model):
    nombre = models.CharField(max_length=30, verbose_name="Nombre del Período")
    fecha_inicio = models.DateField(verbose_name="Fecha Inicio")
    fecha_fin = models.DateField(verbose_name="Fecha Fin")
    trimestre = models.IntegerField(choices=[(1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')], verbose_name="Trimestre")
    dias_computables = models.IntegerField(default=60, verbose_name="Días Hábiles Computables")
    estado = models.CharField(max_length=15, default="En curso", choices=[("En curso", "En curso"), ("Cerrado", "Cerrado")])

    class Meta:
        verbose_name = "Período de Medición"
        verbose_name_plural = "Períodos de Medición"

    def __str__(self):
        return f"{self.nombre} (T{self.trimestre})"

class MetaInstitucional(models.Model):
    nombre = models.CharField(max_length=100, verbose_name="Meta Institucional")
    descripcion = models.CharField(max_length=255, null=True, blank=True, verbose_name="Descripción")
    ponderacion = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Ponderación (%)")
    periodo = models.ForeignKey(Periodo, on_delete=models.RESTRICT, related_name="metas")
    delegacion = models.ForeignKey(Delegacion, on_delete=models.RESTRICT, related_name="metas")

    class Meta:
        verbose_name = "Meta Institucional"
        verbose_name_plural = "Metas Institucionales"

    def __str__(self):
        return f"{self.nombre} ({self.delegacion.nombre} - {self.ponderacion}%)"

class Cumplimiento(models.Model):
    meta = models.ForeignKey(MetaInstitucional, on_delete=models.CASCADE, related_name="cumplimientos")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Porcentaje Cumplido (%)")
    fecha_calculo = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Cálculo")

    class Meta:
        verbose_name = "Registro de Cumplimiento"
        verbose_name_plural = "Registros de Cumplimiento"

    def __str__(self):
        return f"{self.meta.nombre}: {self.porcentaje}% [{self.fecha_calculo:%d/%m/%Y}]"

class ItemMedicion(models.Model):
    meta = models.ForeignKey(MetaInstitucional, on_delete=models.CASCADE, related_name="items_medicion")
    nombre = models.CharField(max_length=100, verbose_name="Indicador / Item de Medición")
    tipo = models.CharField(max_length=50, verbose_name="Tipo de Operación")
    unidad_medida = models.CharField(max_length=50, verbose_name="Unidad de Medida")
    linea_base = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Línea Base")
    valor_objetivo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Valor Objetivo")

    class Meta:
        verbose_name = "Ítem de Medición"
        verbose_name_plural = "Ítems de Medición"

    def __str__(self):
        return f"{self.nombre} ({self.unidad_medida}) - Meta: {self.valor_objetivo}"
