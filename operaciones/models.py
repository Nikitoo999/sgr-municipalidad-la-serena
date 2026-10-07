from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from sgr_core.models import BaseModel, InstitutionalGoal, Delegation

ROLE_CHOICES = [
    ("jefatura", "Jefatura"),
    ("usuario", "Usuario"),
]

# ... aquí siguen tus clases Task, Activity, etc.

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

class Activity(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="activities", verbose_name="Tarea de Agenda")
    name = models.CharField(max_length=100, verbose_name="Nombre de la Actividad")
    execution_date = models.DateField(verbose_name="Fecha de Ejecución")

    class Meta:
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"
        db_table = "actividad"

    def __str__(self):
        return self.name

class Evidence(BaseModel):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="evidences", verbose_name="Actividad Respaldada")
    image_url = models.CharField(max_length=255, verbose_name="URL de Imagen/Archivo")
    is_validated = models.BooleanField(default=False, verbose_name="Validado por Jefatura")

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
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="usuario", verbose_name="Rol")

    class Meta:
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"
        db_table = "funcionario"

    def __str__(self):
        # Si el usuario no tiene nombre configurado, mostrará el username
        nombre = self.user.get_full_name() or self.user.username
        return f"{nombre} - {self.delegation.name}"


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
