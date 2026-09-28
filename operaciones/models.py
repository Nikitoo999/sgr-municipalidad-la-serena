from django.db import models
from django.contrib.auth.models import User
from sgr_core.models import BaseModel, InstitutionalGoal, Delegation

# ... aquí siguen tus clases Task, Activity, etc.

class Task(BaseModel):
    goal = models.ForeignKey(InstitutionalGoal, on_delete=models.CASCADE, related_name="tasks", verbose_name="Meta Institucional")
    title = models.CharField(max_length=200, verbose_name="Título de la Tarea")
    description = models.TextField(blank=True, null=True, verbose_name="Descripción")
    due_date = models.DateField(verbose_name="Fecha de Plazo")
    status = models.CharField(max_length=50, choices=[('Pendiente', 'Pendiente'), ('En Progreso', 'En Progreso'), ('Completada', 'Completada')], default='Pendiente', verbose_name="Estado")

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
    delegation = models.ForeignKey(Delegation, on_delete=models.RESTRICT, related_name='employees', verbose_name="Delegación Asignada")

    class Meta:
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"
        db_table = "funcionario"

    def __str__(self):
        # Si el usuario no tiene nombre configurado, mostrará el username
        nombre = self.user.get_full_name() or self.user.username
        return f"{nombre} - {self.delegation.name}"