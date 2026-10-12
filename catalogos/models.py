from django.db import models

from sgr_core.models import BaseModel


class AttentionType(BaseModel):
    """Catálogo: Tipo de Atención (ej. Social, Territorial, Comunitaria)."""
    name = models.CharField(max_length=80, unique=True, verbose_name="Nombre")
    description = models.TextField(blank=True, default="", verbose_name="Descripción")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Tipo de Atención"
        verbose_name_plural = "Tipos de Atención"
        db_table = "tipo_atencion"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AttentionSubtype(BaseModel):
    """Catálogo: Sub Atención. Cada una pertenece a un Tipo de Atención."""
    attention_type = models.ForeignKey(
        AttentionType, on_delete=models.RESTRICT,
        related_name="subtypes", verbose_name="Tipo de Atención",
    )
    name = models.CharField(max_length=80, verbose_name="Nombre")
    description = models.TextField(blank=True, default="", verbose_name="Descripción")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Sub Atención"
        verbose_name_plural = "Sub Atenciones"
        db_table = "sub_atencion"
        ordering = ["attention_type__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["attention_type", "name"],
                name="uniq_subatencion_por_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.attention_type.name} › {self.name}"
