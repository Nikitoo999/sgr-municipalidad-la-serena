-- =============================================================================
-- RESULTS MANAGEMENT SYSTEM (SGR) - MUNICIPALIDAD DE LA SERENA
-- DATABASE CREATION SCRIPT (ENGLISH VERSION)
-- =============================================================================

DROP DATABASE IF EXISTS sgr_municipalidad_laserena;
CREATE DATABASE sgr_municipalidad_laserena
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_spanish_ci;

USE sgr_municipalidad_laserena;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. BASE TABLES
-- -----------------------------------------------------------------------------

-- Original: rol
CREATE TABLE role (
    role_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(30) NOT NULL UNIQUE,
    description VARCHAR(255) NULL
) ENGINE=InnoDB;

-- Original: permiso
CREATE TABLE permission (
    permission_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) NULL
) ENGINE=InnoDB;

-- Original: cargo
CREATE TABLE position (
    position_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    hierarchical_level INT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

-- Original: delegacion
CREATE TABLE delegation (
    delegation_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'Active'
) ENGINE=InnoDB;

-- Original: periodo
CREATE TABLE period (
    period_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(30) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    quarter INT NOT NULL,
    computable_days INT NOT NULL DEFAULT 60,
    status VARCHAR(15) NOT NULL DEFAULT 'Ongoing'
) ENGINE=InnoDB;

-- Original: atencion_social
CREATE TABLE social_service (
    service_id INT AUTO_INCREMENT PRIMARY KEY,
    national_id VARCHAR(12) NOT NULL, -- Equivalente a RUT
    attended_user_name VARCHAR(100) NOT NULL,
    management_type VARCHAR(100) NULL,
    result VARCHAR(50) NULL,
    registration_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. ASSOCIATIVE & FIRST-LEVEL DEPENDENCIES
-- -----------------------------------------------------------------------------

-- Original: rol_permiso
CREATE TABLE role_permission (
    role_permission_id INT AUTO_INCREMENT PRIMARY KEY,
    role_id INT NOT NULL,
    permission_id INT NOT NULL,
    CONSTRAINT fk_role_permission_role FOREIGN KEY (role_id) REFERENCES role(role_id) ON DELETE CASCADE,
    CONSTRAINT fk_role_permission_perm FOREIGN KEY (permission_id) REFERENCES permission(permission_id) ON DELETE CASCADE,
    UNIQUE KEY uq_role_permission (role_id, permission_id)
) ENGINE=InnoDB;

-- Original: funcionario
CREATE TABLE employee (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    national_id VARCHAR(12) NOT NULL UNIQUE, -- Equivalente a RUT
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    phone VARCHAR(20) NULL,
    photo_url VARCHAR(255) NULL,
    status VARCHAR(15) NOT NULL DEFAULT 'Active',
    role_id INT NOT NULL,
    position_id INT NOT NULL,
    delegation_id INT NOT NULL,
    CONSTRAINT fk_employee_role FOREIGN KEY (role_id) REFERENCES role(role_id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_pos FOREIGN KEY (position_id) REFERENCES position(position_id) ON DELETE RESTRICT,
    CONSTRAINT fk_employee_del FOREIGN KEY (delegation_id) REFERENCES delegation(delegation_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Original: meta
CREATE TABLE goal (
    goal_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    weighting DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    period_id INT NOT NULL,
    delegation_id INT NOT NULL,
    CONSTRAINT fk_goal_period FOREIGN KEY (period_id) REFERENCES period(period_id) ON DELETE RESTRICT,
    CONSTRAINT fk_goal_delegation FOREIGN KEY (delegation_id) REFERENCES delegation(delegation_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 3. SECOND-LEVEL DEPENDENCIES
-- -----------------------------------------------------------------------------

-- Original: cumplimiento
CREATE TABLE achievement (
    achievement_id INT AUTO_INCREMENT PRIMARY KEY,
    goal_id INT NOT NULL,
    percentage DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    calculation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_achievement_goal FOREIGN KEY (goal_id) REFERENCES goal(goal_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Original: item_medicion
CREATE TABLE metric (
    metric_id INT AUTO_INCREMENT PRIMARY KEY,
    goal_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    unit_of_measure VARCHAR(50) NOT NULL,
    baseline DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    target_value DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    CONSTRAINT fk_metric_goal FOREIGN KEY (goal_id) REFERENCES goal(goal_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Original: compromiso
CREATE TABLE commitment (
    commitment_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Entered',
    requester VARCHAR(100) NULL,
    territory VARCHAR(100) NULL,
    support_area VARCHAR(100) NULL,
    deadline DATE NOT NULL,
    employee_id INT NOT NULL,
    goal_id INT NULL,
    CONSTRAINT fk_commitment_emp FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE RESTRICT,
    CONSTRAINT fk_commitment_goal FOREIGN KEY (goal_id) REFERENCES goal(goal_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 4. OPERATIONAL TABLES
-- -----------------------------------------------------------------------------

-- Original: actividad
CREATE TABLE activity (
    activity_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Entered',
    deadline DATE NULL,
    action VARCHAR(255) NULL,
    contact_name VARCHAR(100) NULL,
    contact_phone VARCHAR(20) NULL,
    employee_id INT NOT NULL,
    metric_id INT NULL,
    service_id INT NULL,
    CONSTRAINT fk_activity_emp FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE RESTRICT,
    CONSTRAINT fk_activity_metric FOREIGN KEY (metric_id) REFERENCES metric(metric_id) ON DELETE SET NULL,
    CONSTRAINT fk_activity_service FOREIGN KEY (service_id) REFERENCES social_service(service_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Original: evidencia
CREATE TABLE evidence (
    evidence_id INT AUTO_INCREMENT PRIMARY KEY,
    activity_id INT NOT NULL,
    verifier_id INT NULL,
    unique_code VARCHAR(50) NOT NULL UNIQUE,
    image_url VARCHAR(255) NOT NULL,
    upload_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    validation_status VARCHAR(30) NOT NULL DEFAULT 'Pending',
    validation_date DATETIME NULL,
    rejection_reason TEXT NULL,
    CONSTRAINT fk_evidence_activity FOREIGN KEY (activity_id) REFERENCES activity(activity_id) ON DELETE CASCADE,
    CONSTRAINT fk_evidence_verifier FOREIGN KEY (verifier_id) REFERENCES employee(employee_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- 5. LOGS & NOTIFICATIONS
-- -----------------------------------------------------------------------------

-- Original: comunicacion
CREATE TABLE communication (
    communication_id INT AUTO_INCREMENT PRIMARY KEY,
    sender_id INT NOT NULL,
    recipient_id INT NOT NULL,
    message VARCHAR(255) NOT NULL,
    date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comm_sender FOREIGN KEY (sender_id) REFERENCES employee(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_comm_recipient FOREIGN KEY (recipient_id) REFERENCES employee(employee_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Original: notificacion
CREATE TABLE notification (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    type VARCHAR(50) NOT NULL,
    message VARCHAR(255) NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notif_emp FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Original: reconocimiento
CREATE TABLE recognition (
    recognition_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    issuer_id INT NOT NULL,
    type VARCHAR(30) NOT NULL,
    comment VARCHAR(255) NOT NULL,
    date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_recog_emp FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_recog_issuer FOREIGN KEY (issuer_id) REFERENCES employee(employee_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Original: reporte
CREATE TABLE report (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    type VARCHAR(50) NOT NULL,
    parameters VARCHAR(100) NULL,
    generation_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    file_url VARCHAR(255) NOT NULL,
    CONSTRAINT fk_report_emp FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Original: auditoria
CREATE TABLE audit_log (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id INT NOT NULL,
    action VARCHAR(50) NOT NULL,
    affected_entity VARCHAR(50) NOT NULL,
    entity_id INT NOT NULL,
    date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_emp FOREIGN KEY (employee_id) REFERENCES employee(employee_id) ON DELETE RESTRICT
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;