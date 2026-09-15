from django.db import models
from django.contrib.auth.hashers import make_password, check_password

class Rol(models.Model):
    nombre = models.CharField(max_length=30, unique=True, verbose_name="Nombre del Rol")
    descripcion = models.CharField(max_length=255, null=True, blank=True, verbose_name="Descripción")

    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.nombre

class Permiso(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre del Permiso")
    descripcion = models.CharField(max_length=255, null=True, blank=True, verbose_name="Descripción")

    class Meta:
        verbose_name = "Permiso"
        verbose_name_plural = "Permisos"

    def __str__(self):
        return self.nombre

class RolPermiso(models.Model):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="permisos_asociados")
    permiso = models.ForeignKey(Permiso, on_delete=models.CASCADE, related_name="roles_asociados")

    class Meta:
        verbose_name = "Asignación Rol-Permiso"
        verbose_name_plural = "Asignaciones Rol-Permiso"
        unique_together = ('rol', 'permiso')

    def __str__(self):
        return f"{self.rol.nombre} - {self.permiso.nombre}"

class Cargo(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Cargo")
    nivel_jerarquico = models.IntegerField(default=1, verbose_name="Nivel Jerárquico")

    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"

    def __str__(self):
        return self.nombre

class Delegacion(models.Model):
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre de la Delegación")
    descripcion = models.CharField(max_length=255, null=True, blank=True, verbose_name="Descripción Territorial")
    estado = models.CharField(max_length=10, default="Activa", choices=[("Activa", "Activa"), ("Inactiva", "Inactiva")])

    class Meta:
        verbose_name = "Delegación"
        verbose_name_plural = "Delegaciones"

    def __str__(self):
        return self.nombre

class Funcionario(models.Model):
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT")
    nombre = models.CharField(max_length=100, verbose_name="Nombres")
    apellidos = models.CharField(max_length=100, verbose_name="Apellidos")
    email = models.EmailField(max_length=100, unique=True, verbose_name="Correo Institucional")
    password_hash = models.CharField(max_length=255, verbose_name="Contraseña (Hash)")
    telefono = models.CharField(max_length=20, null=True, blank=True, verbose_name="Teléfono")
    foto_url = models.CharField(max_length=255, null=True, blank=True, verbose_name="Foto / Avatar URL")
    estado = models.CharField(max_length=15, default="Activo", choices=[("Activo", "Activo"), ("Inactivo", "Inactivo")])
    rol = models.ForeignKey(Rol, on_delete=models.RESTRICT, related_name="funcionarios")
    cargo = models.ForeignKey(Cargo, on_delete=models.RESTRICT, related_name="funcionarios")
    delegacion = models.ForeignKey(Delegacion, on_delete=models.RESTRICT, related_name="funcionarios")

    class Meta:
        verbose_name = "Funcionario"
        verbose_name_plural = "Funcionarios"

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def __str__(self):
        return f"{self.nombre} {self.apellidos} ({self.rut})"

class Auditoria(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.RESTRICT, related_name="auditorias")
    accion = models.CharField(max_length=50, verbose_name="Acción Realizada")
    entidad_afectada = models.CharField(max_length=50, verbose_name="Entidad Afectada")
    entidad_id = models.IntegerField(verbose_name="ID de la Entidad")
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y Hora")

    class Meta:
        verbose_name = "Registro de Auditoría"
        verbose_name_plural = "Registros de Auditoría"

    def __str__(self):
        return f"[{self.fecha:%d/%m/%Y %H:%M}] {self.funcionario.email}: {self.accion} on {self.entidad_afectada}#{self.entidad_id}"

class Notificacion(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="notificaciones")
    tipo = models.CharField(max_length=50, verbose_name="Tipo de Notificación")
    mensaje = models.CharField(max_length=255, verbose_name="Mensaje")
    leido = models.BooleanField(default=False, verbose_name="Leído")
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"

    def __str__(self):
        return f"Notif a {self.funcionario.nombre}: {self.mensaje[:30]}"

class Comunicacion(models.Model):
    remitente = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="mensajes_enviados")
    destinatario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="mensajes_recibidos")
    mensaje = models.CharField(max_length=255, verbose_name="Mensaje Interno")
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Envío")

    class Meta:
        verbose_name = "Comunicación Interna"
        verbose_name_plural = "Comunicaciones Internas"

    def __str__(self):
        return f"De {self.remitente.nombre} para {self.destinatario.nombre}"

class Reconocimiento(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.CASCADE, related_name="reconocimientos_recibidos")
    emisor = models.ForeignKey(Funcionario, on_delete=models.RESTRICT, related_name="reconocimientos_emitidos")
    tipo = models.CharField(max_length=30, choices=[("Felicitación", "Felicitación"), ("Reclamo", "Reclamo")])
    comentario = models.CharField(max_length=255, verbose_name="Comentario")
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    class Meta:
        verbose_name = "Reconocimiento"
        verbose_name_plural = "Reconocimientos"

    def __str__(self):
        return f"{self.tipo} a {self.funcionario.nombre}: {self.comentario[:30]}"
