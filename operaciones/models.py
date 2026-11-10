import os
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import get_valid_filename
from portal.validators import validate_attachment_file, validate_image_file
from sgr_core.models import (
    AttentionSubtype,
    AttentionType,
    BaseModel,
    InstitutionalGoal,
    Position,
    Delegation,
    ProjectItem,
    Role,
)


# --- Rutas de los archivos subidos (Bloque 2A) -------------------------------
# El archivo se guarda con el código del registro como prefijo, así se
# reconoce a qué atención o tarea pertenece aunque se descargue o se mueva:
#   atenciones/imagenes/2026/11/ATN-0001_evidencia.jpg
# Las funciones viven a nivel de módulo porque las migraciones las referencian.

def _code_prefixed_path(folder, code, filename):
    """``<carpeta>/<AAAA>/<MM>/<codigo>_<archivo>`` con un nombre seguro."""
    original = os.path.basename(filename or "") or "archivo"
    safe_name = get_valid_filename(original) or "archivo"
    now = timezone.localtime()
    return f"{folder}/{now:%Y}/{now:%m}/{code}_{safe_name}"


def attention_image_path(instance, filename):
    """Imagen de evidencia: ``atenciones/imagenes/AAAA/MM/ATN-0001_<archivo>``."""
    return _code_prefixed_path("atenciones/imagenes", instance.number or "ATN-sn", filename)


def attention_attachment_path(instance, filename):
    """Documento de respaldo: ``atenciones/adjuntos/AAAA/MM/ATN-0001_<archivo>``."""
    return _code_prefixed_path("atenciones/adjuntos", instance.number or "ATN-sn", filename)




class Task(BaseModel):
    goal = models.ForeignKey(InstitutionalGoal, on_delete=models.CASCADE, related_name="tasks", verbose_name="Meta Institucional")
    title = models.CharField(max_length=200, verbose_name="Título de la Tarea")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    due_date = models.DateField(verbose_name="Fecha de Plazo")
    status = models.CharField(max_length=50, choices=[('Pendiente', 'Pendiente'), ('En Progreso', 'En Progreso'), ('Completada', 'Completada')], default='Pendiente', verbose_name="Estado")
    assigned_to = models.ForeignKey(
        "Employee", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_tasks", verbose_name="Responsable asignado",
    )

    class Meta:
        verbose_name = "Tarea"
        verbose_name_plural = "Tareas"
        db_table = "tarea_agenda"

    def __str__(self):
        return f"{self.title} - {self.status}"

    @property
    def code(self):
        """Código de la tarea; identifica la carpeta de sus evidencias (TAR-00012)."""
        return f"TAR-{self.pk:05d}" if self.pk else ""

class Activity(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="activities", verbose_name="Tarea de Agenda")
    name = models.CharField(max_length=100, verbose_name="Nombre de la Actividad")
    execution_date = models.DateField(verbose_name="Fecha de Ejecución")
    item = models.ForeignKey(
    ProjectItem, on_delete=models.SET_NULL, null=True, blank=True,
    related_name="activities", verbose_name="Ítem de la matriz",
    )

    class Status(models.TextChoices):
        PENDING = "Pendiente", "Pendiente"
        DONE = "Realizada", "Realizada"

    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING, verbose_name="Estado",
    )

    class Meta:
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"
        db_table = "actividad"

    def __str__(self):
        return self.name

def evidence_upload_to(instance, filename):
    """Guarda la evidencia bajo el código de su tarea: evidencias/TAR-00012/archivo."""
    return f"evidencias/{instance.activity.task.code}/{filename}"

class Evidence(BaseModel):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="evidences", verbose_name="Actividad Respaldada")
    image_url = models.CharField(max_length=255, blank=True, default="", verbose_name="URL de Imagen/Archivo")
    file = models.FileField(
        upload_to=evidence_upload_to, max_length=255, blank=True, null=True,
        validators=[validate_attachment_file], verbose_name="Archivo de evidencia (máx. 5 MB)",
    )
    is_validated = models.BooleanField(default=False, verbose_name="Validado por Jefatura")
    validated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="validated_evidences", verbose_name="Validado por",
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de validación")


    class Meta:
        verbose_name = "Evidencia"
        verbose_name_plural = "Evidencias"
        db_table = "evidencia"

    def __str__(self):
        return f"Evidencia para: {self.activity.name}"

class Employee(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee', verbose_name="Usuario de Sistema")
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono")
    address = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección")
    delegation = models.ForeignKey(Delegation, on_delete=models.RESTRICT, related_name='employees', verbose_name="Delegación Asignada")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='employees', verbose_name="Rol")
    position = models.ForeignKey(Position, on_delete=models.PROTECT, null=True, blank=True,related_name="employees", verbose_name="Cargo",)
    authorized_delegations = models.ManyToManyField(Delegation, blank=True, related_name='authorized_employees', verbose_name="Delegaciones autorizadas")
    must_change_password = models.BooleanField(default=False, verbose_name="Debe cambiar contraseña al ingresar")

    class Meta:
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"
        db_table = "funcionario"

    def __str__(self):
        # Si el usuario no tiene nombre configurado, mostrará el username
        nombre = self.user.get_full_name() or self.user.username
        return f"{nombre} - {self.delegation.name}"

    def save(self, *args, **kwargs):
        """Borrado lógico del funcionario: desactiva también la cuenta.

        El motor de mantenedores marca ``deleted_at`` para borrar de forma
        lógica. En Usuarios eso debe impedir el acceso, así que la cuenta
        (``User``) queda ``is_active=False``. Nunca hay borrado físico.
        """
        marcando_borrado = (
            self.pk is not None
            and self.deleted_at is not None
            and self.user_id is not None
        )
        if marcando_borrado:
            User.objects.filter(pk=self.user_id).update(is_active=False)
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Nombre visible del funcionario (nombre + apellido, o el username)."""
        return self.user.get_full_name() or self.user.username

    @property
    def email(self):
        """Correo de la cuenta asociada."""
        return self.user.email

    @property
    def status_label(self):
        """Estado en texto (Activo/Inactivo) derivado de ``user.is_active``."""
        return "Activo" if self.user.is_active else "Inactivo"

    @property
    def role_code(self):
        """Código del rol asignado (columna del listado y exportación)."""
        return self.role.code if self.role_id else ""

    @property
    def delegations(self):
        """Delegaciones del funcionario para las insignias del listado.

        Siempre un queryset: con alcance 'Delegaciones autorizadas' son las
        autorizadas (que incluyen la base); en cualquier otro caso, solo la
        delegación base.
        """
        authorized = self.authorized_delegations.filter(deleted_at__isnull=True)
        if authorized.exists():
            return authorized.order_by("code")
        if self.delegation_id is None:
            return Delegation.objects.none()
        return Delegation.objects.filter(pk=self.delegation_id)

    def allowed_delegations(self):
        """Delegaciones que este funcionario puede gestionar según su rol.

        - scope all: todas las delegaciones activas.
        - scope authorized: las delegaciones autorizadas; si no tiene ninguna
        declarada, solo su delegación base.
        - own_delegation / own_records: solo su delegación base.
        """
        if self.role_id is None:
            return []
        scope = self.role.scope
        if scope == "all":
            return list(Delegation.objects.filter(status="Activa", deleted_at__isnull=True).order_by("name"))
        if scope == "authorized":
            authorized = list(self.authorized_delegations.filter(deleted_at__isnull=True))
            return authorized if authorized else [self.delegation]
        return [self.delegation]

    def clean(self):
        super().clean()
        if self.role_id is None or self.delegation_id is None:
            return
        if self.role.scope in ("own_delegation", "own_records") and self.pk:
            extras = [
                delegation for delegation in self.authorized_delegations.all()
                if delegation.pk != self.delegation_id
            ]
            if extras:
                raise ValidationError({
                    "authorized_delegations": (
                        "Los roles con alcance 'Su delegación' o 'Solo registros propios' "
                        "no admiten delegaciones autorizadas distintas de su delegación base."
                    ),
                })


class TaskReassignment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="reassignments", verbose_name="Tarea Derivada")
    original_employee = models.ForeignKey(Employee, on_delete=models.RESTRICT, related_name="original_reassignments", verbose_name="Funcionario Original")
    reassigned_employee = models.ForeignKey(Employee, on_delete=models.RESTRICT, related_name="received_reassignments", verbose_name="Funcionario Receptor")
    reason = models.CharField(max_length=20, choices=[("vacation", "Vacaciones"), ("absence", "Ausencia"), ("other", "Otro")], verbose_name="Motivo de la Derivación")
    reassigned_at = models.DateTimeField(verbose_name="Fecha de Derivación")
    notes = models.TextField(blank=True, null=True, verbose_name="Observaciones")

    class Meta:
        verbose_name = "Derivación de tarea"
        verbose_name_plural = "Derivaciones de tareas"
        db_table = "derivacion_tarea"

    def __str__(self):
        return f"{self.task.title} ({self.original_employee} a {self.reassigned_employee})"


class Benefit(BaseModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="benefits", verbose_name="Funcionario Beneficiario")
    benefit_type = models.CharField(max_length=30, choices=[("food_basket", "Canasta de alimentos"), ("school_kit", "Kit escolar"), ("medical_aid", "Ayuda médica"), ("other", "Otro")], verbose_name="Tipo de Beneficio")
    delivery_area = models.ForeignKey(Delegation, on_delete=models.RESTRICT, related_name="delivered_benefits", verbose_name="Delegación de Entrega")
    delivered_at = models.DateTimeField(blank=True, null=True, verbose_name="Fecha de Entrega")
    delivered = models.BooleanField(default=False, verbose_name="Entregado")

    class Meta:
        verbose_name = "Beneficio"
        verbose_name_plural = "Beneficios"
        db_table = "beneficio"

    def clean(self):
        super().clean()
        if self.employee_id and self.delivery_area_id and self.delivery_area != self.employee.delegation:
            raise ValidationError({
                "delivery_area": "La delegación de entrega debe coincidir con la delegación del funcionario.",
            })

    def __str__(self):
        return f"{self.employee} - {self.get_benefit_type_display()} ({self.delivery_area.name})"


NEIGHBOR_STATUS_CHOICES = [("Activo", "Activo"), ("Inactivo", "Inactivo")]


class Neighbor(BaseModel):
    """Vecino o solicitante de una atención."""

    identifier = models.CharField(max_length=20, unique=True, verbose_name="Identificador (RUT u otro)")
    full_name = models.CharField(max_length=150, verbose_name="Nombre completo")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono")
    email = models.EmailField(blank=True, default="", verbose_name="Correo electrónico")
    status = models.CharField(max_length=10, choices=NEIGHBOR_STATUS_CHOICES, default="Activo", verbose_name="Estado")

    class Meta:
        verbose_name = "Vecino"
        verbose_name_plural = "Vecinos"
        db_table = "vecino"

    def __str__(self):
        return f"{self.full_name} ({self.identifier})"


class Attention(BaseModel):
    """Atención ciudadana ingresada por un funcionario.

    Bloque 2B: el vecino se identifica con RUT, nombre y teléfono obligatorios
    (``Neighbor``), se marca si requiere visita a terreno, admite el estado
    "Sin resolver" (dar de baja con motivo obligatorio), hasta 3 gestiones de
    seguimiento (``AttentionFollowUp``) y guarda si suma al puntaje operativo
    (los ingresos del rol Delegado no suman). Ver ``operaciones.rules``.
    """

    class AttentionStatus(models.TextChoices):
        RECEIVED = "received", "Ingresada"
        IN_PROGRESS = "in_progress", "En gestión"
        RESOLVED = "resolved", "Resuelta"
        UNRESOLVED = "unresolved", "Sin resolver"

    number = models.CharField(max_length=12, unique=True, null=True, blank=True, verbose_name="Número de atención")
    neighbor = models.ForeignKey(
        Neighbor, on_delete=models.RESTRICT,
        related_name="attentions", verbose_name="Vecino o solicitante",
    )
    delegation = models.ForeignKey(
        Delegation, on_delete=models.RESTRICT,
        related_name="attentions", verbose_name="Delegación",
    )
    attention_type = models.ForeignKey(
        AttentionType, on_delete=models.RESTRICT,
        related_name="attentions", verbose_name="Tipo de atención",
    )
    attention_subtype = models.ForeignKey(
        AttentionSubtype, on_delete=models.RESTRICT,
        related_name="attentions", verbose_name="Sub atención",
    )
    description = models.TextField(verbose_name="Descripción")
    responsible = models.ForeignKey(
        User, on_delete=models.RESTRICT,
        related_name="attentions", verbose_name="Funcionario responsable",
    )
    status = models.CharField(
        max_length=20, choices=AttentionStatus.choices,
        default=AttentionStatus.RECEIVED, verbose_name="Estado",
    )
    requires_visit = models.BooleanField(
        default=False, verbose_name="Requiere visita a terreno",
    )
    unresolved_reason = models.TextField(
        blank=True, default="", verbose_name="Motivo de baja (Sin resolver)",
    )
    counts_for_score = models.BooleanField(
        default=True, verbose_name="Cuenta para el puntaje operativo",
        help_text="Las atenciones ingresadas por el rol Delegado no suman al puntaje operativo.",
    )
    evidence_image = models.ImageField(
        upload_to=attention_image_path, max_length=255, blank=True, null=True,
        validators=[validate_image_file], verbose_name="Imagen de evidencia (máx. 2 MB)",
    )
    attachment = models.FileField(
        upload_to=attention_attachment_path, max_length=255, blank=True, null=True,
        validators=[validate_attachment_file], verbose_name="Documento de respaldo (máx. 5 MB)",
    )

    #: Campos de archivo que llevan el número de la atención como prefijo.
    FILE_FIELDS = ("evidence_image", "attachment")

    class Meta:
        verbose_name = "Atención"
        verbose_name_plural = "Atenciones"
        db_table = "atencion"
        indexes = [
            models.Index(fields=["delegation", "created_at"], name="idx_atencion_deleg_fecha"),
            models.Index(fields=["responsible"], name="idx_atencion_responsable"),
            models.Index(fields=["status"], name="idx_atencion_estado"),
            models.Index(fields=["attention_type", "attention_subtype"], name="idx_atencion_tipo_subtipo"),
        ]

    def __str__(self):
        return f"{self.number or 's/n'} - {self.neighbor}"

    @property
    def created_at_display(self):
        """Fecha y hora legible de la atención (columna del listado)."""
        if self.created_at is None:
            return "—"
        return timezone.localtime(self.created_at).strftime("%d-%m-%Y %H:%M")

    @property
    def solicitante_name(self):
        """Nombre del vecino o solicitante (columna y exportación)."""
        return self.neighbor.full_name if self.neighbor_id else "—"

    @property
    def type_name(self):
        """Nombre del tipo de atención."""
        return self.attention_type.name if self.attention_type_id else "—"

    @property
    def subtype_name(self):
        """Nombre de la sub atención."""
        return self.attention_subtype.name if self.attention_subtype_id else "—"

    @property
    def delegation_label(self):
        """Código y nombre de la delegación (exportación)."""
        if self.delegation_id is None:
            return "—"
        return f"{self.delegation.code} · {self.delegation.name}"

    @property
    def responsible_name(self):
        """Nombre visible del funcionario responsable."""
        if self.responsible_id is None:
            return "—"
        return self.responsible.get_full_name() or self.responsible.username

    @property
    def status_display(self):
        """Estado en texto (Ingresada/En gestión/Resuelta/Sin resolver)."""
        return self.get_status_display()

    @property
    def neighbor_rut(self):
        return self.neighbor.identifier if self.neighbor_id else "—"

    @property
    def neighbor_phone(self):
        return (self.neighbor.phone or "—") if self.neighbor_id else "—"

    @property
    def requires_visit_display(self):
        return "Sí" if self.requires_visit else "No"

    @property
    def score_display(self):
        """Texto del puntaje operativo (columna de exportación y consulta)."""
        if self.counts_for_score:
            return "Cuenta"
        return "No cuenta (ingreso del rol Delegado)"

    def save(self, *args, **kwargs):
        """Asigna number (formato ATN-0001) tras el primer insert.

        El número se deriva del id dentro de una transacción; el segundo
        guardado usa update_fields para no re-entrar en este método.

        Al crear, los archivos nuevos se apartan durante el primer INSERT
        (todavía no hay número) y se guardan en el segundo guardado, cuando
        el número ya existe: así el archivo queda como ``ATN-0001_foto.jpg``.
        """
        creating = self._state.adding
        pending_files = {}
        if creating:
            for name in self.FILE_FIELDS:
                value = getattr(self, name)
                if value and not getattr(value, "_committed", True):
                    pending_files[name] = value
                    setattr(self, name, None)
        with transaction.atomic():
            super().save(*args, **kwargs)
            update_fields = []
            if creating and not self.number:
                self.number = f"ATN-{self.pk:04d}"
                update_fields.append("number")
            for name, value in pending_files.items():
                setattr(self, name, value)
                update_fields.append(name)
            if update_fields:
                super().save(update_fields=update_fields, using=kwargs.get("using"))

class EmployeeDayOff(BaseModel):
    """Día(s) libre(s) de un funcionario; ajusta la meta del trimestre."""

    class Kind(models.TextChoices):
        VACATION = "vacation", "Vacaciones"
        LICENSE = "license", "Licencia médica"
        ADMINISTRATIVE = "administrative", "Día administrativo"
        EMERGENCY = "emergency", "Emergencia"
        COMPENSATORY = "compensatory", "Compensatorio"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name="days_off", verbose_name="Funcionario",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Tipo")
    start_date = models.DateField(verbose_name="Desde")
    end_date = models.DateField(verbose_name="Hasta")
    notes = models.CharField(max_length=200, blank=True, default="", verbose_name="Observaciones")
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="registered_days_off", verbose_name="Registrado por",
    )

    class Meta:
        verbose_name = "Día libre"
        verbose_name_plural = "Días libres"
        db_table = "dia_libre_funcionario"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee} - {self.get_kind_display()} ({self.start_date} a {self.end_date})"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La fecha final no puede ser anterior a la inicial."})

    @property
    def business_days(self):
        """Días hábiles (lunes a viernes) que cubre este registro."""
        total, day = 0, self.start_date
        while day <= self.end_date:
            if day.weekday() < 5:
                total += 1
            day += timedelta(days=1)
        return total

class EmployeeFeedback(BaseModel):
    """Felicitación (suma) o reclamo (resta) asociado a un funcionario."""

    class Kind(models.TextChoices):
        PRAISE = "praise", "Felicitación"
        COMPLAINT = "complaint", "Reclamo"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE,
        related_name="feedbacks", verbose_name="Funcionario",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, verbose_name="Tipo")
    date = models.DateField(verbose_name="Fecha")
    description = models.CharField(max_length=255, verbose_name="Descripción")
    file = models.FileField(
        upload_to="respaldos/%Y/%m/", max_length=255, blank=True, null=True,
        validators=[validate_attachment_file], verbose_name="Respaldo formal (máx. 5 MB)",
    )
    registered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="registered_feedbacks", verbose_name="Registrado por",
    )

    class Meta:
        verbose_name = "Felicitación o reclamo"
        verbose_name_plural = "Felicitaciones y reclamos"
        db_table = "felicitacion_reclamo"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_kind_display()} - {self.employee} ({self.date})"

    def clean(self):
        super().clean()
        if self.kind == self.Kind.PRAISE and not self.file:
            raise ValidationError({"file": "Una felicitación solo suma puntaje con respaldo formal."})

def generate_verification_code():
    """Código corto que debe verse en la foto de respaldo (sin caracteres ambiguos)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(6))


class TubeEntry(BaseModel):
    """Solicitud o trabajo del tubo (delegación, Antena o Cartas)."""

    class Channel(models.TextChoices):
        DELEGATION = "delegation", "Tubo de la delegación"
        ANTENNA = "antenna", "Tubo Antena"
        LETTERS = "letters", "Tubo Cartas"

    class Status(models.TextChoices):
        RECEIVED = "received", "Ingresado"
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En proceso"
        DONE = "done", "Realizado"
        NOT_APPLICABLE = "not_applicable", "No aplica"

    class Origin(models.TextChoices):
        INTERNAL = "INT", "Interno"
        EXTERNAL = "EXT", "Externo"

    delegation = models.ForeignKey(
        Delegation, on_delete=models.RESTRICT,
        related_name="tube_entries", verbose_name="Delegación",
    )
    channel = models.CharField(
        max_length=12, choices=Channel.choices, default=Channel.DELEGATION, verbose_name="Canal",
    )
    title = models.CharField(max_length=255, verbose_name="Actividad / solicitud / problema")
    origin = models.CharField(max_length=3, choices=Origin.choices, default=Origin.EXTERNAL, verbose_name="Interno o externo")
    requester = models.CharField(max_length=150, verbose_name="Solicitante")
    territory = models.CharField(max_length=60, blank=True, default="", verbose_name="Territorio")
    responsible = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tube_entries", verbose_name="Responsable",
    )
    request_date = models.DateField(verbose_name="Fecha de solicitud")
    due_date = models.DateField(null=True, blank=True, verbose_name="Fecha de compromiso")
    support_area = models.CharField(max_length=100, blank=True, default="", verbose_name="Área o persona de apoyo")
    notes = models.TextField(blank=True, default="", verbose_name="Avance y observaciones")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.RECEIVED, verbose_name="Estatus")
    letter_number = models.CharField(max_length=20, blank=True, default="", verbose_name="N° de carta")
    contact_phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Teléfono de contacto")
    verification_code = models.CharField(
        max_length=8, default=generate_verification_code, editable=False,
        verbose_name="Código de verificación",
    )
    proof_image = models.ImageField(
        upload_to="tubos/%Y/%m/", max_length=255, blank=True, null=True,
        validators=[validate_image_file], verbose_name="Foto de respaldo (máx. 2 MB)",
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de realización")

    class Meta:
        verbose_name = "Solicitud del tubo"
        verbose_name_plural = "Tubos"
        db_table = "tubo"
        ordering = ["-request_date", "-pk"]
        indexes = [
            models.Index(fields=["delegation", "channel", "status"], name="idx_tubo_deleg_canal_estado"),
        ]

    def __str__(self):
        return f"{self.code} - {self.title}"

    @property
    def code(self):
        """Código de la solicitud (TUB-00012)."""
        return f"TUB-{self.pk:05d}" if self.pk else ""

    def clean(self):
        super().clean()
        if self.status == self.Status.DONE and not self.proof_image:
            raise ValidationError({"proof_image": "Para marcar como Realizado hay que subir la foto de respaldo."})

class AttentionFollowUp(BaseModel):
    """Gestión de seguimiento de una atención (Bloque 2B, máximo 3).

    Registra lo que se hizo después del ingreso (llamada, visita, derivación,
    respuesta al vecino). Una gestión NO es una atención nueva: no suma al
    puntaje operativo ni cuenta para el tope diario de ingresos. El máximo de
    3 lo validan ``operaciones.rules.register_follow_up`` y, además, la base
    de datos (correlativo único por atención y CHECK entre 1 y 3).
    """

    attention = models.ForeignKey(
        Attention, on_delete=models.CASCADE,
        related_name="follow_ups", verbose_name="Atención",
    )
    sequence = models.PositiveSmallIntegerField(verbose_name="N° de gestión")
    description = models.TextField(verbose_name="Detalle de la gestión")
    performed_by = models.ForeignKey(
        User, on_delete=models.RESTRICT,
        related_name="attention_follow_ups", verbose_name="Registrada por",
    )

    class Meta:
        verbose_name = "Gestión de seguimiento"
        verbose_name_plural = "Gestiones de seguimiento"
        db_table = "gestion_atencion"
        ordering = ["attention", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["attention", "sequence"], name="uniq_gestion_atencion_secuencia",
            ),
            models.CheckConstraint(
                condition=models.Q(sequence__gte=1) & models.Q(sequence__lte=3),
                name="chk_gestion_atencion_max_3",
            ),
        ]

    def __str__(self):
        return f"{self.attention.number} · gestión {self.sequence}"

    @property
    def created_at_display(self):
        if self.created_at is None:
            return "—"
        return timezone.localtime(self.created_at).strftime("%d-%m-%Y %H:%M")

    @property
    def performed_by_name(self):
        if self.performed_by_id is None:
            return "—"
        return self.performed_by.get_full_name() or self.performed_by.username


class WeeklyClosure(BaseModel):
    """Cierre semanal de atenciones de una delegación (Bloque 2B).

    La semana va de lunes a domingo (``week_start`` siempre es lunes). Con la
    semana cerrada no se ingresan ni se editan atenciones de esa semana en esa
    delegación. Reabrir la semana es un borrado lógico del cierre; si se
    vuelve a cerrar, se reutiliza el mismo registro.
    """

    delegation = models.ForeignKey(
        Delegation, on_delete=models.RESTRICT,
        related_name="weekly_closures", verbose_name="Delegación",
    )
    week_start = models.DateField(verbose_name="Semana (lunes)")
    closed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="weekly_closures", verbose_name="Cerrada por",
    )
    closed_at = models.DateTimeField(default=timezone.now, verbose_name="Fecha de cierre")
    notes = models.CharField(max_length=200, blank=True, default="", verbose_name="Observación")

    class Meta:
        verbose_name = "Cierre semanal"
        verbose_name_plural = "Cierres semanales"
        db_table = "cierre_semanal"
        ordering = ["-week_start", "delegation__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["delegation", "week_start"], name="uniq_cierre_semanal_deleg_semana",
            ),
        ]

    def __str__(self):
        return f"{self.delegation.code} · semana {self.week_start:%d-%m-%Y}"

    @property
    def week_end(self):
        return self.week_start + timedelta(days=6)

    def clean(self):
        super().clean()
        if self.week_start and self.week_start.weekday() != 0:
            raise ValidationError({"week_start": "La semana debe comenzar un lunes."})
