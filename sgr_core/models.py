from django.db import models

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última modificación")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de eliminación")

    class Meta:
        abstract = True

class Delegation(BaseModel):
    code = models.CharField(max_length=10, unique=True, null=True, blank=True, verbose_name="Código")
    name = models.CharField(max_length=50, verbose_name="Nombre de Delegación")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección")
    commune = models.CharField(max_length=100, default="La Serena", verbose_name="Comuna")
    is_active = models.BooleanField(default=True, verbose_name="Activa")
    color = models.CharField(max_length=7, blank=True, default="", help_text="Código hex, ej: #E63946", verbose_name="Color distintivo")

    class Meta:
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"
        db_table = "delegacion"

    def __str__(self):
        return f"{self.code} - {self.name}" if self.code else self.name


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


# ======================= Seguridad: permisos y roles =======================
class Permission(models.Model):
    """Permiso funcional del sistema (p. ej. 'user.create'). Se carga con `seed_roles`."""
    codename = models.CharField(max_length=50, unique=True, verbose_name="Código")
    name = models.CharField(max_length=120, verbose_name="Descripción")

    class Meta:
        verbose_name = "Permiso"
        verbose_name_plural = "Permisos"
        db_table = "permiso"
        ordering = ("codename",)

    def __str__(self):
        return self.name


class Role(BaseModel):
    SCOPE_ALL = "all"
    SCOPE_DELEGATIONS = "delegations"
    SCOPE_OWN = "own"
    SCOPE_CHOICES = [
        (SCOPE_ALL, "Todas las delegaciones"),
        (SCOPE_DELEGATIONS, "Delegaciones autorizadas"),
        (SCOPE_OWN, "Solo su delegación"),
    ]

    code = models.CharField(max_length=30, unique=True, verbose_name="Código")
    name = models.CharField(max_length=60, unique=True, verbose_name="Nombre")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="Descripción")
    scope = models.CharField(max_length=15, choices=SCOPE_CHOICES, default=SCOPE_OWN, verbose_name="Alcance autorizado")
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles", verbose_name="Permisos")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        db_table = "rol"
        ordering = ("code",)

    def __str__(self):
        return self.name


# ======================= Catálogos de atención ciudadana =======================
class AttentionType(BaseModel):
    code = models.CharField(max_length=10, unique=True, verbose_name="Código")
    name = models.CharField(max_length=80, unique=True, verbose_name="Nombre")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="Descripción")
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Tipo de Atención"
        verbose_name_plural = "Tipos de Atención"
        db_table = "tipo_atencion"
        ordering = ("code",)

    def __str__(self):
        return self.name


class AttentionSubtype(BaseModel):
    code = models.CharField(max_length=10, unique=True, verbose_name="Código")
    name = models.CharField(max_length=80, verbose_name="Nombre")
    attention_type = models.ForeignKey(AttentionType, on_delete=models.PROTECT, related_name="subtypes", verbose_name="Tipo de Atención")
    is_active = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Sub Atención"
        verbose_name_plural = "Sub Atenciones"
        db_table = "sub_atencion"
        ordering = ("code",)
        constraints = [
            models.UniqueConstraint(fields=("attention_type", "name"), name="uniq_subatencion_tipo_nombre"),
        ]

    def __str__(self):
        return self.name


class Requester(BaseModel):
    """Solicitante (vecino) de una atención ciudadana."""
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    full_name = models.CharField(max_length=150, verbose_name="Nombre completo")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono")
    email = models.EmailField(blank=True, default="", verbose_name="Correo")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección")

    class Meta:
        verbose_name = "Solicitante"
        verbose_name_plural = "Solicitantes"
        db_table = "solicitante"
        ordering = ("full_name",)

    def __str__(self):
        return f"{self.full_name} ({self.rut})"
