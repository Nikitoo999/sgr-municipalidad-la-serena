from django.db import models
from rrhh.models import Funcionario
from sgr_core.models import MetaInstitucional, ItemMedicion

class AtencionSocial(models.Model):
    rut_usuario_atendido = models.CharField(max_length=12, verbose_name="RUT Vecino Atendido")
    nombre_usuario_atendido = models.CharField(max_length=100, verbose_name="Nombre Vecino Atendido")
    tipo_gestion = models.CharField(max_length=100, null=True, blank=True, verbose_name="Tipo de Gestión")
    resultado = models.CharField(max_length=50, null=True, blank=True, verbose_name="Resultado / Resolución")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Atención")

    class Meta:
        verbose_name = "Atención Social"
        verbose_name_plural = "Atenciones Sociales"

    def __str__(self):
        return f"{self.nombre_usuario_atendido} ({self.rut_usuario_atendido}) - {self.tipo_gestion}"

class Compromiso(models.Model):
    titulo = models.CharField(max_length=150, verbose_name="Título del Compromiso")
    estado = models.CharField(max_length=30, default="Ingresado", choices=[
        ("Ingresado", "Ingresado"),
        ("En curso", "En curso"),
        ("Finalizado", "Finalizado"),
        ("Postergado", "Postergado")
    ])
    solicitante = models.CharField(max_length=100, null=True, blank=True, verbose_name="Solicitante / Junta Vecinal")
    territorio = models.CharField(max_length=100, null=True, blank=True, verbose_name="Territorio / Sector")
    area_apoyo = models.CharField(max_length=100, null=True, blank=True, verbose_name="Área de Apoyo")
    fecha_limite = models.DateField(verbose_name="Fecha Límite")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.RESTRICT, related_name="compromisos")
    meta = models.ForeignKey(MetaInstitucional, on_delete=models.SET_NULL, null=True, blank=True, related_name="compromisos")

    class Meta:
        verbose_name = "Compromiso Territorial"
        verbose_name_plural = "Agenda de Compromisos"

    def __str__(self):
        return f"{self.titulo} [{self.estado}] - Resp: {self.funcionario.nombre}"

class Actividad(models.Model):
    nombre = models.CharField(max_length=150, verbose_name="Nombre de la Actividad")
    descripcion = models.TextField(null=True, blank=True, verbose_name="Descripción")
    estado = models.CharField(max_length=30, default="Ingresado", choices=[
        ("Ingresado", "Ingresado"),
        ("En proceso", "En proceso"),
        ("Realizado", "Realizado"),
        ("Suspendido", "Suspendido")
    ])
    fecha_limite = models.DateField(null=True, blank=True, verbose_name="Fecha Límite")
    accion = models.CharField(max_length=255, null=True, blank=True, verbose_name="Acción a Realizar")
    contacto_nombre = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nombre Contacto")
    contacto_fono = models.CharField(max_length=20, null=True, blank=True, verbose_name="Teléfono Contacto")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.RESTRICT, related_name="actividades")
    item_medicion = models.ForeignKey(ItemMedicion, on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades")
    atencion_social = models.ForeignKey(AtencionSocial, on_delete=models.SET_NULL, null=True, blank=True, related_name="actividades")

    class Meta:
        verbose_name = "Actividad Operativa"
        verbose_name_plural = "Actividades Operativas"

    def __str__(self):
        return f"{self.nombre} ({self.estado})"

class Evidencia(models.Model):
    actividad = models.ForeignKey(Actividad, on_delete=models.CASCADE, related_name="evidencias")
    verificador = models.ForeignKey(Funcionario, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias_verificadas")
    codigo_unico = models.CharField(max_length=50, unique=True, verbose_name="Código Único (Ej: EV-0412)")
    imagen_url = models.CharField(max_length=255, verbose_name="URL Fotografía")
    fecha_subida = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Subida")
    estado_validacion = models.CharField(max_length=30, default="Pendiente", choices=[
        ("Pendiente", "Pendiente"),
        ("Aprobada", "Aprobada"),
        ("Observada", "Observada"),
        ("Rechazada", "Rechazada")
    ])
    fecha_validacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Validación")
    motivo_rechazo = models.TextField(null=True, blank=True, verbose_name="Motivo de Rechazo / Observación")

    class Meta:
        verbose_name = "Evidencia Fotográfica"
        verbose_name_plural = "Evidencias Fotográficas"

    def __str__(self):
        return f"{self.codigo_unico} [{self.estado_validacion}] - Actividad: {self.actividad.nombre}"
