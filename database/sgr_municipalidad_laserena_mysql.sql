-- =============================================================================
-- SISTEMA DE GESTIÓN DE RESULTADOS (SGR) - MUNICIPALIDAD DE LA SERENA
-- SCRIPT DE CREACIÓN DE BASE DE DATOS Y ESTRUCTURA RELACIONAL (MySQL 8.0+)
-- Asignatura: Proyecto Integrado / Programación Back End (INACAP)
-- =============================================================================

DROP DATABASE IF EXISTS sgr_municipalidad_laserena;
CREATE DATABASE sgr_municipalidad_laserena
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_spanish_ci;

USE sgr_municipalidad_laserena;

-- Desactivar temporalmente revisión de claves foráneas para limpieza segura
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 1. TABLAS BASE INDEPENDIENTES (Sin dependencias de clave foránea)
-- -----------------------------------------------------------------------------

-- 1.1 Tabla: Rol
CREATE TABLE rol (
    rol_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL UNIQUE,
    descripcion VARCHAR(255) NULL
) ENGINE=InnoDB;

-- 1.2 Tabla: Permiso
CREATE TABLE permiso (
    permiso_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(255) NULL
) ENGINE=InnoDB;

-- 1.3 Tabla: Cargo
CREATE TABLE cargo (
    cargo_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    nivel_jerarquico INT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

-- 1.4 Tabla: Delegacion
CREATE TABLE delegacion (
    delegacion_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(255) NULL,
    estado VARCHAR(10) NOT NULL DEFAULT 'Activa'
) ENGINE=InnoDB;

-- 1.5 Tabla: Periodo
CREATE TABLE periodo (
    periodo_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    trimestre INT NOT NULL,
    dias_computables INT NOT NULL DEFAULT 60,
    estado VARCHAR(15) NOT NULL DEFAULT 'En curso'
) ENGINE=InnoDB;

-- 1.6 Tabla: Atencion_Social
CREATE TABLE atencion_social (
    atencion_id INT AUTO_INCREMENT PRIMARY KEY,
    rut_usuario_atendido VARCHAR(12) NOT NULL,
    nombre_usuario_atendido VARCHAR(100) NOT NULL,
    tipo_gestion VARCHAR(100) NULL,
    resultado VARCHAR(50) NULL,
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 2. TABLAS ASOCIATIVAS Y DEPENDIENTES DE PRIMER NIVEL
-- -----------------------------------------------------------------------------

-- 2.1 Tabla Intermedia: RolPermiso (N:M entre Rol y Permiso)
CREATE TABLE rol_permiso (
    rolpermiso_id INT AUTO_INCREMENT PRIMARY KEY,
    rol_id INT NOT NULL,
    permiso_id INT NOT NULL,
    CONSTRAINT fk_rolpermiso_rol FOREIGN KEY (rol_id) REFERENCES rol(rol_id) ON DELETE CASCADE,
    CONSTRAINT fk_rolpermiso_permiso FOREIGN KEY (permiso_id) REFERENCES permiso(permiso_id) ON DELETE CASCADE,
    UNIQUE KEY uq_rol_permiso (rol_id, permiso_id)
) ENGINE=InnoDB;

-- 2.2 Tabla: Funcionario
CREATE TABLE funcionario (
    funcionario_id INT AUTO_INCREMENT PRIMARY KEY,
    rut VARCHAR(12) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    telefono VARCHAR(20) NULL,
    foto_url VARCHAR(255) NULL,
    estado VARCHAR(15) NOT NULL DEFAULT 'Activo',
    rol_id INT NOT NULL,
    cargo_id INT NOT NULL,
    delegacion_id INT NOT NULL,
    CONSTRAINT fk_funcionario_rol FOREIGN KEY (rol_id) REFERENCES rol(rol_id) ON DELETE RESTRICT,
    CONSTRAINT fk_funcionario_cargo FOREIGN KEY (cargo_id) REFERENCES cargo(cargo_id) ON DELETE RESTRICT,
    CONSTRAINT fk_funcionario_delegacion FOREIGN KEY (delegacion_id) REFERENCES delegacion(delegacion_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 2.3 Tabla: Meta (Planificación de delegación por período)
CREATE TABLE meta (
    meta_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255) NULL,
    ponderacion DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    periodo_id INT NOT NULL,
    delegacion_id INT NOT NULL,
    CONSTRAINT fk_meta_periodo FOREIGN KEY (periodo_id) REFERENCES periodo(periodo_id) ON DELETE RESTRICT,
    CONSTRAINT fk_meta_delegacion FOREIGN KEY (delegacion_id) REFERENCES delegacion(delegacion_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 3. TABLAS DEPENDIENTES DE SEGUNDO NIVEL (Metas, Mediciones y Compromisos)
-- -----------------------------------------------------------------------------

-- 3.1 Tabla: Cumplimiento (Seguimiento de cumplimiento por meta)
CREATE TABLE cumplimiento (
    cumplimiento_id INT AUTO_INCREMENT PRIMARY KEY,
    meta_id INT NOT NULL,
    porcentaje DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    fecha_calculo DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cumplimiento_meta FOREIGN KEY (meta_id) REFERENCES meta(meta_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 3.2 Tabla: Item_Medicion (Indicadores que componen una meta)
CREATE TABLE item_medicion (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    meta_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    unidad_medida VARCHAR(50) NOT NULL,
    linea_base DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    valor_objetivo DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_item_meta FOREIGN KEY (meta_id) REFERENCES meta(meta_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 3.3 Tabla: Compromiso (Agenda colectiva municipal)
CREATE TABLE compromiso (
    compromiso_id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(150) NOT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'Ingresado',
    solicitante VARCHAR(100) NULL,
    territorio VARCHAR(100) NULL,
    area_apoyo VARCHAR(100) NULL,
    fecha_limite DATE NOT NULL,
    funcionario_id INT NOT NULL,
    meta_id INT NULL,
    CONSTRAINT fk_compromiso_funcionario FOREIGN KEY (funcionario_id) REFERENCES funcionario(funcionario_id) ON DELETE RESTRICT,
    CONSTRAINT fk_compromiso_meta FOREIGN KEY (meta_id) REFERENCES meta(meta_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 4. TABLAS OPERATIVAS: ACTIVIDADES Y EVIDENCIAS
-- -----------------------------------------------------------------------------

-- 4.1 Tabla: Actividad
CREATE TABLE actividad (
    actividad_id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT NULL,
    estado VARCHAR(30) NOT NULL DEFAULT 'Ingresado',
    fecha_limite DATE NULL,
    accion VARCHAR(255) NULL,
    contacto_nombre VARCHAR(100) NULL,
    contacto_fono VARCHAR(20) NULL,
    funcionario_id INT NOT NULL,
    item_id INT NULL,
    atencion_id INT NULL,
    CONSTRAINT fk_actividad_funcionario FOREIGN KEY (funcionario_id) REFERENCES funcionario(funcionario_id) ON DELETE RESTRICT,
    CONSTRAINT fk_actividad_item FOREIGN KEY (item_id) REFERENCES item_medicion(item_id) ON DELETE SET NULL,
    CONSTRAINT fk_actividad_atencion FOREIGN KEY (atencion_id) REFERENCES atencion_social(atencion_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 4.2 Tabla: Evidencia (Archivos y fotografías de respaldo)
CREATE TABLE evidencia (
    evidencia_id INT AUTO_INCREMENT PRIMARY KEY,
    actividad_id INT NOT NULL,
    verificador_id INT NULL,
    codigo_unico VARCHAR(50) NOT NULL UNIQUE,
    imagen_url VARCHAR(255) NOT NULL,
    fecha_subida DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado_validacion VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    fecha_validacion DATETIME NULL,
    motivo_rechazo TEXT NULL,
    CONSTRAINT fk_evidencia_actividad FOREIGN KEY (actividad_id) REFERENCES actividad(actividad_id) ON DELETE CASCADE,
    CONSTRAINT fk_evidencia_verificador FOREIGN KEY (verificador_id) REFERENCES funcionario(funcionario_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- -----------------------------------------------------------------------------
-- 5. COMUNICACIÓN, REPORTABILIDAD, RECONOCIMIENTOS Y AUDITORÍA
-- -----------------------------------------------------------------------------

-- 5.1 Tabla: Comunicacion (Mensajería interna)
CREATE TABLE comunicacion (
    comunicacion_id INT AUTO_INCREMENT PRIMARY KEY,
    remitente_id INT NOT NULL,
    destinatario_id INT NOT NULL,
    mensaje VARCHAR(255) NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comunicacion_remitente FOREIGN KEY (remitente_id) REFERENCES funcionario(funcionario_id) ON DELETE CASCADE,
    CONSTRAINT fk_comunicacion_destinatario FOREIGN KEY (destinatario_id) REFERENCES funcionario(funcionario_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 5.2 Tabla: Notificacion
CREATE TABLE notificacion (
    notificacion_id INT AUTO_INCREMENT PRIMARY KEY,
    funcionario_id INT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    mensaje VARCHAR(255) NOT NULL,
    leido BOOLEAN NOT NULL DEFAULT FALSE,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notificacion_funcionario FOREIGN KEY (funcionario_id) REFERENCES funcionario(funcionario_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 5.3 Tabla: Reconocimiento (Felicitaciones y Reclamos)
CREATE TABLE reconocimiento (
    reconocimiento_id INT AUTO_INCREMENT PRIMARY KEY,
    funcionario_id INT NOT NULL,
    emisor_id INT NOT NULL,
    tipo VARCHAR(30) NOT NULL,
    comentario VARCHAR(255) NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reconocimiento_funcionario FOREIGN KEY (funcionario_id) REFERENCES funcionario(funcionario_id) ON DELETE CASCADE,
    CONSTRAINT fk_reconocimiento_emisor FOREIGN KEY (emisor_id) REFERENCES funcionario(funcionario_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 5.4 Tabla: Reporte
CREATE TABLE reporte (
    reporte_id INT AUTO_INCREMENT PRIMARY KEY,
    funcionario_id INT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    parametros VARCHAR(100) NULL,
    fecha_generacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    archivo_url VARCHAR(255) NOT NULL,
    CONSTRAINT fk_reporte_funcionario FOREIGN KEY (funcionario_id) REFERENCES funcionario(funcionario_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 5.5 Tabla: Auditoria (Trazabilidad y gobernanza inmutable)
CREATE TABLE auditoria (
    auditoria_id INT AUTO_INCREMENT PRIMARY KEY,
    funcionario_id INT NOT NULL,
    accion VARCHAR(50) NOT NULL,
    entidad_afectada VARCHAR(50) NOT NULL,
    entidad_id INT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_auditoria_funcionario FOREIGN KEY (funcionario_id) REFERENCES funcionario(funcionario_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Reactivar revisión de claves foráneas
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------------------------------
-- 6. DATOS DE PRUEBA (SEED DATA PARA DEMOSTRACIÓN)
-- -----------------------------------------------------------------------------

-- Roles
INSERT INTO rol (rol_id, nombre, descripcion) VALUES
(1, 'Administrador', 'Control total de usuarios, roles y configuración'),
(2, 'Gerencia', 'Visualización de las 6 delegaciones y reportes consolidados'),
(3, 'Delegado', 'Jefatura de delegación territorial'),
(4, 'Funcionario', 'Ejecutor de actividades en terreno'),
(5, 'Verificador', 'Validador de evidencias fotográficas');

-- Cargos
INSERT INTO cargo (cargo_id, nombre, nivel_jerarquico) VALUES
(1, 'Alcalde / Administrador Municipal', 1),
(2, 'Jefe de Delegación Territorial', 2),
(3, 'Supervisor de Operaciones', 3),
(4, 'Inspector Municipal', 4),
(5, 'Asistente Social', 4);

-- Delegaciones
INSERT INTO delegacion (delegacion_id, nombre, descripcion, estado) VALUES
(1, 'Centro', 'Delegación Municipal Sector Centro Histórico', 'Activa'),
(2, 'Avenida del Mar', 'Delegación Costera y Borde Marítimo', 'Activa'),
(3, 'Las Compañías', 'Delegación Sector Norte', 'Activa'),
(4, 'La Pampa', 'Delegación Sector Sur Residencial', 'Activa'),
(5, 'La Antena - La Florida', 'Delegación Sector Oriente', 'Activa'),
(6, 'Rural', 'Delegación Comunidades y Pueblos Rurales', 'Activa');

-- Periodo
INSERT INTO periodo (periodo_id, nombre, fecha_inicio, fecha_fin, trimestre, dias_computables, estado) VALUES
(1, 'Tercer Trimestre 2026', '2026-07-01', '2026-09-30', 3, 62, 'En curso');

-- Funcionarios
INSERT INTO funcionario (funcionario_id, rut, nombre, apellidos, email, password_hash, estado, rol_id, cargo_id, delegacion_id) VALUES
(1, '15.421.980-3', 'Alan', 'Von Kretschmann', 'a.vonkretschmann@laserena.cl', 'pbkdf2_sha256$hash123', 'Activo', 3, 2, 1),
(2, '14.892.311-K', 'Rodrigo', 'Fuenzalida Vásquez', 'r.fuenzalida@laserena.cl', 'pbkdf2_sha256$hash123', 'Activo', 3, 2, 2),
(3, '16.711.204-5', 'Pablo', 'Cuadra Corrales', 'p.cuadra@laserena.cl', 'pbkdf2_sha256$hash123', 'Activo', 3, 2, 3),
(4, '17.332.901-2', 'Romina', 'Bravo Sepúlveda', 'r.bravo@laserena.cl', 'pbkdf2_sha256$hash123', 'Activo', 4, 4, 1),
(5, '18.112.450-8', 'Camilo', 'Miranda Toro', 'c.miranda@laserena.cl', 'pbkdf2_sha256$hash123', 'Activo', 5, 3, 1);

-- Metas
INSERT INTO meta (meta_id, nombre, descripcion, ponderacion, periodo_id, delegacion_id) VALUES
(1, 'Mantención Vial Urbana', 'Bacheo y demarcación vial en casco histórico', 35.00, 1, 1),
(2, 'Mantenimiento de Áreas Verdes', 'Poda y arborización urbana', 35.00, 1, 1),
(3, 'Atención y Cobertura Social', 'Operativos y atenciones comunitarias', 30.00, 1, 1);

-- Items de Medición
INSERT INTO item_medicion (item_id, meta_id, nombre, tipo, unidad_medida, linea_base, valor_objetivo) VALUES
(1, 1, 'Bacheo asfáltico', 'Operativo', 'Metros lineales', 50.00, 300.00),
(2, 2, 'Poda de árboles mayores', 'Preventivo', 'Unidades', 20.00, 120.00),
(3, 3, 'Atenciones sociales en terreno', 'Social', 'Casos resueltos', 10.00, 80.00);

-- Actividades
INSERT INTO actividad (actividad_id, nombre, descripcion, estado, fecha_limite, funcionario_id, item_id) VALUES
(1, 'Bacheo calle Cienfuegos cuadra 2', 'Reparación de pavimento dañado reportado por vecinos', 'En proceso', '2026-09-15', 1, 1),
(2, 'Poda preventiva Av. Francisco de Aguirre', 'Despeje de luminarias y calzada', 'Realizado', '2026-09-12', 4, 2);

-- Evidencias
INSERT INTO evidencia (evidencia_id, actividad_id, verificador_id, codigo_unico, imagen_url, estado_validacion) VALUES
(1, 1, 5, 'EV-0412', 'https://storage.laserena.cl/evidencias/IMG-TC0148-01.jpg', 'Pendiente'),
(2, 2, 5, 'EV-0413', 'https://storage.laserena.cl/evidencias/IMG-TC0146-02.jpg', 'Aprobada');
