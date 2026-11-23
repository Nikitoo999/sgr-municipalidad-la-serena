from django.db import IntegrityError, models, transaction
from django.db.models import IntegerField, Max
from django.db.models.functions import Cast, Substr

from .roles import ACTIONS, MODULES, SCOPES, SCOPE_RANKS

DELEGATION_STATUS_CHOICES = [("Activa", "Activa"), ("Inactiva", "Inactiva")]
ROLE_STATUS_CHOICES = [("Activo", "Activo"), ("Inactivo", "Inactivo")]
CATALOG_STATUS_CHOICES = [("Activo", "Activo"), ("Inactivo", "Inactivo")]


class AutoCodeMixin:
    """Código correlativo automático del mantenedor (DEL01, ROL01, ITM001...).

    Cada modelo declara ``CODE_PREFIX`` y ``CODE_DIGITS``. Al crear un registro
    sin código, ``save()`` busca en la base de datos el mayor correlativo con
    ese prefijo (incluidos los eliminados de forma lógica, porque ``code`` es
    único en toda la tabla), le suma 1 y guarda dentro de
    ``transaction.atomic()``. Si dos personas guardan a la vez y les toca el
    mismo número, la restricción ``unique`` rechaza el segundo INSERT y se
    reintenta con el siguiente número.

    Si el código ya viene informado (datos demo, migraciones o pruebas) se
    respeta tal cual: solo se genera cuando falta.
    """

    CODE_PREFIX = ""
    CODE_DIGITS = 2
    CODE_MAX_ATTEMPTS = 5

    @classmethod
    def next_code(cls):
        """Siguiente código libre, por ejemplo ``DEL07`` o ``ITM008``.

        El máximo se calcula en la base de datos (sin traer filas a Python):
        solo cuentan los códigos con el formato ``<PREFIJO><dígitos>``.
        """
        prefix = cls.CODE_PREFIX
        last = (
            cls.objects.filter(code__regex=rf"^{prefix}[0-9]+$")
            .annotate(_correlativo=Cast(Substr("code", len(prefix) + 1), IntegerField()))
            .aggregate(maximo=Max("_correlativo"))["maximo"]
        ) or 0
        return f"{prefix}{last + 1:0{cls.CODE_DIGITS}d}"

    def save(self, *args, **kwargs):
        if not self._state.adding or self.code:
            return super().save(*args, **kwargs)
        for _attempt in range(self.CODE_MAX_ATTEMPTS):
            self.code = type(self).next_code()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                # Solo se reintenta si el choque fue por el código.
                if not type(self).objects.filter(code=self.code).exists():
                    raise
        raise IntegrityError(
            f"No se pudo asignar un código correlativo con el prefijo {self.CODE_PREFIX}."
        )


class AliveQuerySet(models.QuerySet):
    """QuerySet que excluye registros con borrado lógico."""

    def alive(self):
        return self.filter(deleted_at__isnull=True)


class AliveManager(models.Manager):
    """Manager adicional que excluye registros con deleted_at no nulo."""

    def get_queryset(self):
        return AliveQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última modificación")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de eliminación")

    # El manager por defecto no cambia (no altera el Admin ni el código
    # existente); "alive" es un manager adicional con borrado lógico.
    objects = models.Manager()
    alive = AliveManager()

    class Meta:
        abstract = True

class Delegation(AutoCodeMixin, BaseModel):
    CODE_PREFIX = "DEL"
    CODE_DIGITS = 2

    name = models.CharField(max_length=50, verbose_name="Nombre de Delegación")
    code = models.CharField(max_length=8, unique=True, verbose_name="Código")
    commune = models.CharField(max_length=80, default="La Serena", verbose_name="Comuna")
    address = models.CharField(max_length=200, blank=True, default="", verbose_name="Dirección")
    status = models.CharField(max_length=10, choices=DELEGATION_STATUS_CHOICES, default="Activa", verbose_name="Estado")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    color = models.CharField(max_length=7, blank=True, default="", help_text="Código hex, ej: #E63946", verbose_name="Color distintivo")

    class Meta:
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"
        db_table = "delegacion"

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.status == "Activa"

class Role(AutoCodeMixin, BaseModel):
    CODE_PREFIX = "ROL"
    CODE_DIGITS = 2

    code = models.CharField(max_length=8, unique=True, verbose_name="Código")
    name = models.CharField(max_length=50, verbose_name="Nombre del Rol")
    description = models.TextField(blank=True, default="", verbose_name="Descripción")
    scope = models.CharField(max_length=20, choices=SCOPES, default="own_records", verbose_name="Alcance")
    status = models.CharField(max_length=10, choices=ROLE_STATUS_CHOICES, default="Activo", verbose_name="Estado")
    is_system = models.BooleanField(default=False, verbose_name="Rol de sistema")

    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        db_table = "rol"

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def rank(self):
        """Rango derivado del alcance: all=3, authorized=2, own_delegation=1, own_records=0."""
        return SCOPE_RANKS.get(self.scope, 0)

    @property
    def scope_label(self):
        """Alcance en texto para el usuario (es-cl), por ejemplo 'Todas las delegaciones'."""
        return dict(SCOPES).get(self.scope, self.scope)

    @property
    def enabled_modules_count(self):
        """Cantidad de módulos con al menos un permiso asignado.

        Property de solo lectura: no es un campo, así que no genera migración.
        """
        return self.permissions.values_list("module", flat=True).distinct().count()

    @property
    def is_active(self):
        return self.status == "Activo"

class RolePermission(BaseModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions", verbose_name="Rol")
    module = models.CharField(max_length=30, choices=MODULES, verbose_name="Módulo")
    action = models.CharField(max_length=20, choices=ACTIONS, verbose_name="Acción")

    class Meta:
        verbose_name = "Permiso de rol"
        verbose_name_plural = "Permisos de roles"
        db_table = "rol_permiso"
        constraints = [
            models.UniqueConstraint(fields=["role", "module", "action"], name="uniq_role_module_action"),
        ]

    def __str__(self):
        return f"{self.role.code}: {self.module}.{self.action}"

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

    @property
    def start_display(self):
        return self.start_date.strftime("%d-%m-%Y") if self.start_date else "—"

    @property
    def end_display(self):
        return self.end_date.strftime("%d-%m-%Y") if self.end_date else "—"

    @property
    def quarter_display(self):
        return f"T{self.quarter} {self.start_date.year}" if self.start_date else f"T{self.quarter}"

    @property
    def business_days(self):
        """Días computables: hábiles de lunes a viernes (RF-005)."""
        from datetime import timedelta

        if not (self.start_date and self.end_date):
            return 0
        total, dia = 0, self.start_date
        while dia <= self.end_date:
            if dia.weekday() < 5:
                total += 1
            dia += timedelta(days=1)
        return total

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


class ProjectItem(AutoCodeMixin, BaseModel):
    """Ítem de proyecto del catálogo (mantenedor Ítems y metas)."""

    CODE_PREFIX = "ITM"
    CODE_DIGITS = 3

    code = models.CharField(max_length=8, unique=True, verbose_name="Código")
    name = models.CharField(max_length=100, verbose_name="Nombre del ítem")
    description = models.TextField(blank=True, default="", verbose_name="Descripción")
    requires_contact = models.BooleanField(
        default=True, verbose_name="Exige nombre y teléfono del usuario",
        help_text=(
            "Nuevo requerimiento, punto 2: las actividades y solicitudes de cara al "
            "usuario sin nombre y teléfono no suman. Desmárcalo en ítems internos "
            "(informes, inventarios, reuniones de equipo)."
        ),
    )
    status = models.CharField(max_length=10, choices=CATALOG_STATUS_CHOICES, default="Activo", verbose_name="Estado")

    class Meta:
        verbose_name = "Ítem de proyecto"
        verbose_name_plural = "Ítems de proyecto"
        db_table = "item_proyecto"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class AttentionType(AutoCodeMixin, BaseModel):
    """Tipo de atención del catálogo (mantenedor Tipo de Atención)."""

    CODE_PREFIX = "TAT"
    CODE_DIGITS = 2

    code = models.CharField(max_length=8, unique=True, verbose_name="Código")
    name = models.CharField(max_length=100, verbose_name="Nombre del tipo")
    description = models.TextField(blank=True, default="", verbose_name="Descripción")
    status = models.CharField(max_length=10, choices=CATALOG_STATUS_CHOICES, default="Activo", verbose_name="Estado")

    class Meta:
        verbose_name = "Tipo de atención"
        verbose_name_plural = "Tipos de atención"
        db_table = "tipo_atencion"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class AttentionSubtype(AutoCodeMixin, BaseModel):
    """Sub atención del catálogo (mantenedor Sub Atención)."""

    CODE_PREFIX = "SAT"
    CODE_DIGITS = 3

    code = models.CharField(max_length=8, unique=True, verbose_name="Código")
    name = models.CharField(max_length=100, verbose_name="Nombre de la sub atención")
    attention_type = models.ForeignKey(
        AttentionType, on_delete=models.RESTRICT,
        related_name="subtypes", verbose_name="Tipo de atención",
    )
    item = models.ForeignKey(
        "ProjectItem", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="suggested_for_subtypes", verbose_name="Ítem sugerido de la matriz",
        help_text=(
            "Ítem que se propone al ingresar una atención de esta sub atención. "
            "Solo se usa si el cargo del funcionario mide ese ítem."
        ),
    )
    scores = models.BooleanField(
        default=True, verbose_name="Suma puntaje",
        help_text=(
            "Desmarcar en gestiones preparatorias (coordinaciones, correos, "
            "invitaciones): el punto se da cuando se realiza la acción."
        ),
    )
    status = models.CharField(max_length=10, choices=CATALOG_STATUS_CHOICES, default="Activo", verbose_name="Estado")

    class Meta:
        verbose_name = "Sub atención"
        verbose_name_plural = "Sub atenciones"
        db_table = "sub_atencion"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def scores_display(self):
        """Texto de la columna "Suma puntaje"."""
        return "Sí" if self.scores else "No (gestión preparatoria)"


class Position(BaseModel):
    """Cargo de delegación según el descriptor de funciones 2026."""

    code = models.CharField(max_length=8, unique=True, verbose_name="Código")
    name = models.CharField(max_length=60, verbose_name="Nombre del cargo")
    summary = models.TextField(blank=True, default="", verbose_name="Resumen del cargo")
    functions = models.TextField(blank=True, default="", verbose_name="Descriptor de funciones")
    is_evaluated = models.BooleanField(default=True, verbose_name="Se evalúa en la matriz")
    status = models.CharField(max_length=10, choices=CATALOG_STATUS_CHOICES, default="Activo", verbose_name="Estado")

    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        db_table = "cargo"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def evaluated_display(self):
        return "Sí" if self.is_evaluated else "No"


class PositionItemGoal(BaseModel):
    """Ponderador y meta de un ítem para un cargo en un trimestre."""

    position = models.ForeignKey(
        Position, on_delete=models.CASCADE,
        related_name="item_goals", verbose_name="Cargo",
    )
    item = models.ForeignKey(
        ProjectItem, on_delete=models.RESTRICT,
        related_name="position_goals", verbose_name="Ítem",
    )
    period = models.ForeignKey(
        Period, on_delete=models.RESTRICT,
        related_name="position_goals", verbose_name="Período",
    )
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="Ponderador (%)")
    target_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="Meta del trimestre")

    class Meta:
        verbose_name = "Meta por cargo"
        verbose_name_plural = "Metas por cargo"
        db_table = "meta_cargo_item"
        ordering = ["position__code", "item__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["position", "item", "period"],
                name="uniq_position_item_period",
            ),
        ]

    def __str__(self):
        return f"{self.position.name} / {self.item.name} ({self.weight}%)"

class CommunityOrganization(BaseModel):
    """Organización comunitaria (juntas de vecinos y organizaciones funcionales)."""

    class Category(models.TextChoices):
        NEIGHBORHOOD = "neighborhood", "Junta de vecinos"
        SENIOR = "senior", "Club de adulto mayor"
        SPORTS = "sports", "Organización deportiva"
        CULTURAL = "cultural", "Centro de madres / cultural / juvenil"
        COMMITTEE = "committee", "Comité"
        OTHER = "other", "Otra organización"

    name = models.CharField(max_length=200, verbose_name="Nombre de la organización")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER, verbose_name="Categoría")
    legal_address = models.CharField(max_length=255, blank=True, default="", verbose_name="Domicilio legal")
    territory = models.CharField(max_length=30, blank=True, default="", verbose_name="Territorio (según la base)")
    delegation = models.ForeignKey(
        Delegation, on_delete=models.RESTRICT, null=True, blank=True,
        related_name="community_organizations", verbose_name="Delegación",
    )
    active_members = models.PositiveIntegerField(null=True, blank=True, verbose_name="Socios activos")
    constitution_date = models.DateField(null=True, blank=True, verbose_name="Fecha de constitución")
    registry_number = models.CharField(max_length=20, blank=True, default="", db_index=True, verbose_name="N° registro P.J.")
    registry_date = models.DateField(null=True, blank=True, verbose_name="Fecha de inscripción en registro")
    directive_number = models.CharField(max_length=20, blank=True, default="", verbose_name="N° registro de directiva")
    verified = models.BooleanField(default=False, verbose_name="Verificada")
    status = models.CharField(max_length=10, choices=CATALOG_STATUS_CHOICES, default="Activo", verbose_name="Estado")
    notes = models.TextField(blank=True, default="", verbose_name="Observaciones de limpieza")

    class Meta:
        verbose_name = "Organización comunitaria"
        verbose_name_plural = "Organizaciones comunitarias"
        db_table = "organizacion_comunitaria"
        ordering = ["name"]

    @property
    def category_label(self):
        return self.get_category_display()

    @property
    def verified_display(self):
        return "Verificada" if self.verified else "Sin verificar"

    @property
    def members_display(self):
        return "—" if self.active_members is None else self.active_members

    @property
    def directiva(self):
        """Integrantes vigentes de la directiva (organigrama), por cargo."""
        return self.members.filter(deleted_at__isnull=True).select_related("role").order_by(
            "role__order", "role__name",
        )

    @property
    def roles_directivos(self):
        """Cargos directivos activos (para asignar integrantes)."""
        return DirectiveRole.objects.filter(deleted_at__isnull=True, status="Activo")

    def __str__(self):
        return self.name


class DirectiveRole(BaseModel):
    """Cargo de la directiva de una organización (Presidente/a, Secretario/a...).

    Los cargos base se cargan con una migración; se pueden crear otros
    (Vicepresidente/a, Encargado/a de Medio Ambiente...).
    """

    name = models.CharField(max_length=60, verbose_name="Cargo directivo")
    is_base = models.BooleanField(default=False, verbose_name="Cargo base")
    order = models.PositiveSmallIntegerField(default=100, verbose_name="Orden en el organigrama")
    status = models.CharField(max_length=10, choices=CATALOG_STATUS_CHOICES, default="Activo", verbose_name="Estado")

    class Meta:
        verbose_name = "Cargo directivo"
        verbose_name_plural = "Cargos directivos"
        db_table = "cargo_directivo"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class OrganizationMember(BaseModel):
    """Integrante de la directiva de una organización (organigrama).

    Una organización tiene a lo más un integrante vigente por cargo: asignar
    el cargo de nuevo reemplaza al anterior (que queda con borrado lógico).
    Los datos personales son de contacto; en la demo deben ser ficticios.
    """

    organization = models.ForeignKey(
        CommunityOrganization, on_delete=models.CASCADE,
        related_name="members", verbose_name="Organización",
    )
    role = models.ForeignKey(
        DirectiveRole, on_delete=models.RESTRICT,
        related_name="members", verbose_name="Cargo directivo",
    )
    full_name = models.CharField(max_length=150, verbose_name="Nombre completo")
    rut = models.CharField(max_length=12, blank=True, default="", verbose_name="RUT")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono")

    class Meta:
        verbose_name = "Integrante de directiva"
        verbose_name_plural = "Integrantes de directiva"
        db_table = "integrante_organizacion"
        ordering = ["role__order", "role__name"]

    def __str__(self):
        return f"{self.role.name}: {self.full_name}"
