-- Esquema SQLite del SGR (generado con python manage.py migrate sobre una base vacia).
-- Base del equipo: db.sqlite3 (no se versiona; cada uno la crea con migrate + seed_demo).

CREATE TABLE "actividad" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "name" varchar(100) NOT NULL, "execution_date" date NOT NULL, "task_id" bigint NOT NULL REFERENCES "tarea_agenda" ("id") DEFERRABLE INITIALLY DEFERRED, "status" varchar(15) NOT NULL, "item_id" bigint NULL REFERENCES "item_proyecto" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "atencion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "number" varchar(12) NULL UNIQUE, "description" text NOT NULL, "status" varchar(20) NOT NULL, "attention_subtype_id" bigint NOT NULL REFERENCES "sub_atencion" ("id") DEFERRABLE INITIALLY DEFERRED, "attention_type_id" bigint NOT NULL REFERENCES "tipo_atencion" ("id") DEFERRABLE INITIALLY DEFERRED, "delegation_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED, "responsible_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "neighbor_id" bigint NOT NULL REFERENCES "vecino" ("id") DEFERRABLE INITIALLY DEFERRED, "evidence_image" varchar(255) NULL, "attachment" varchar(255) NULL, "counts_for_score" bool NOT NULL, "requires_visit" bool NOT NULL, "unresolved_reason" text NOT NULL);

CREATE TABLE "auth_group" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "name" varchar(150) NOT NULL UNIQUE);

CREATE TABLE "auth_group_permissions" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "group_id" integer NOT NULL REFERENCES "auth_group" ("id") DEFERRABLE INITIALLY DEFERRED, "permission_id" integer NOT NULL REFERENCES "auth_permission" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "auth_permission" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "content_type_id" integer NOT NULL REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED, "codename" varchar(100) NOT NULL, "name" varchar(255) NOT NULL);

CREATE TABLE "auth_user" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "password" varchar(128) NOT NULL, "last_login" datetime NULL, "is_superuser" bool NOT NULL, "username" varchar(150) NOT NULL UNIQUE, "last_name" varchar(150) NOT NULL, "email" varchar(254) NOT NULL, "is_staff" bool NOT NULL, "is_active" bool NOT NULL, "date_joined" datetime NOT NULL, "first_name" varchar(150) NOT NULL);

CREATE TABLE "auth_user_groups" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "group_id" integer NOT NULL REFERENCES "auth_group" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "auth_user_user_permissions" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "permission_id" integer NOT NULL REFERENCES "auth_permission" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "beneficio" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "benefit_type" varchar(30) NOT NULL, "delivered_at" datetime NULL, "delivered" bool NOT NULL, "delivery_area_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED, "employee_id" bigint NOT NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "cargo" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "code" varchar(8) NOT NULL UNIQUE, "name" varchar(60) NOT NULL, "summary" text NOT NULL, "functions" text NOT NULL, "is_evaluated" bool NOT NULL, "status" varchar(10) NOT NULL);

CREATE TABLE "cierre_semanal" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "week_start" date NOT NULL, "closed_at" datetime NOT NULL, "notes" varchar(200) NOT NULL, "closed_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "delegation_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "uniq_cierre_semanal_deleg_semana" UNIQUE ("delegation_id", "week_start"));

CREATE TABLE "cumplimiento" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "percentage" decimal NOT NULL, "goal_id" bigint NOT NULL REFERENCES "meta" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "delegacion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "name" varchar(50) NOT NULL, "description" text NULL, "color" varchar(7) NOT NULL, "address" varchar(200) NOT NULL, "commune" varchar(80) NOT NULL, "status" varchar(10) NOT NULL, "code" varchar(8) NOT NULL UNIQUE);

CREATE TABLE "derivacion_tarea" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "reason" varchar(20) NOT NULL, "reassigned_at" datetime NOT NULL, "notes" text NULL, "original_employee_id" bigint NOT NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED, "reassigned_employee_id" bigint NOT NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED, "task_id" bigint NOT NULL REFERENCES "tarea_agenda" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "dia_libre_funcionario" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "kind" varchar(20) NOT NULL, "start_date" date NOT NULL, "end_date" date NOT NULL, "notes" varchar(200) NOT NULL, "employee_id" bigint NOT NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED, "registered_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "django_admin_log" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "object_id" text NULL, "object_repr" varchar(200) NOT NULL, "action_flag" smallint unsigned NOT NULL CHECK ("action_flag" >= 0), "change_message" text NOT NULL, "content_type_id" integer NULL REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED, "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "action_time" datetime NOT NULL);

CREATE TABLE "django_content_type" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "app_label" varchar(100) NOT NULL, "model" varchar(100) NOT NULL);

CREATE TABLE "django_migrations" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "app" varchar(255) NOT NULL, "name" varchar(255) NOT NULL, "applied" datetime NOT NULL);

CREATE TABLE "django_session" ("session_key" varchar(40) NOT NULL PRIMARY KEY, "session_data" text NOT NULL, "expire_date" datetime NOT NULL);

CREATE TABLE "evidencia" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "is_validated" bool NOT NULL, "activity_id" bigint NOT NULL REFERENCES "actividad" ("id") DEFERRABLE INITIALLY DEFERRED, "file" varchar(255) NULL, "validated_at" datetime NULL, "validated_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "image_url" varchar(255) NOT NULL);

CREATE TABLE "felicitacion_reclamo" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "kind" varchar(10) NOT NULL, "date" date NOT NULL, "description" varchar(255) NOT NULL, "file" varchar(255) NULL, "employee_id" bigint NOT NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED, "registered_by_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "funcionario" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "rut" varchar(12) NOT NULL UNIQUE, "phone" varchar(20) NULL, "delegation_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED, "user_id" integer NOT NULL UNIQUE REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "address" varchar(255) NOT NULL, "role_id" bigint NOT NULL REFERENCES "rol" ("id") DEFERRABLE INITIALLY DEFERRED, "must_change_password" bool NOT NULL, "position_id" bigint NULL REFERENCES "cargo" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "funcionario_authorized_delegations" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "employee_id" bigint NOT NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED, "delegation_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "gestion_atencion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "sequence" smallint unsigned NOT NULL CHECK ("sequence" >= 0), "description" text NOT NULL, "attention_id" bigint NOT NULL REFERENCES "atencion" ("id") DEFERRABLE INITIALLY DEFERRED, "performed_by_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "uniq_gestion_atencion_secuencia" UNIQUE ("attention_id", "sequence"), CONSTRAINT "chk_gestion_atencion_max_3" CHECK (("sequence" >= 1 AND "sequence" <= 3)));

CREATE TABLE "item_medicion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "name" varchar(100) NOT NULL, "unit_of_measure" varchar(50) NOT NULL, "baseline" decimal NOT NULL, "target_value" decimal NOT NULL, "goal_id" bigint NOT NULL REFERENCES "meta" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "item_proyecto" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "code" varchar(8) NOT NULL UNIQUE, "name" varchar(100) NOT NULL, "description" text NOT NULL, "status" varchar(10) NOT NULL);

CREATE TABLE "meta" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "name" varchar(100) NOT NULL, "description" text NULL, "weight" decimal NOT NULL, "delegation_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED, "period_id" bigint NOT NULL REFERENCES "periodo" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "meta_cargo_item" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "weight" decimal NOT NULL, "target_value" decimal NOT NULL, "item_id" bigint NOT NULL REFERENCES "item_proyecto" ("id") DEFERRABLE INITIALLY DEFERRED, "period_id" bigint NOT NULL REFERENCES "periodo" ("id") DEFERRABLE INITIALLY DEFERRED, "position_id" bigint NOT NULL REFERENCES "cargo" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "uniq_position_item_period" UNIQUE ("position_id", "item_id", "period_id"));

CREATE TABLE "organizacion_comunitaria" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "name" varchar(200) NOT NULL, "category" varchar(20) NOT NULL, "legal_address" varchar(255) NOT NULL, "territory" varchar(30) NOT NULL, "active_members" integer unsigned NULL CHECK ("active_members" >= 0), "constitution_date" date NULL, "registry_number" varchar(20) NOT NULL, "registry_date" date NULL, "directive_number" varchar(20) NOT NULL, "verified" bool NOT NULL, "status" varchar(10) NOT NULL, "notes" text NOT NULL, "delegation_id" bigint NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "periodo" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "name" varchar(30) NOT NULL, "start_date" date NOT NULL, "end_date" date NOT NULL, "quarter" integer NOT NULL, "status" varchar(15) NOT NULL);

CREATE TABLE "portal_audit_log" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "action" varchar(50) NOT NULL, "module" varchar(50) NOT NULL, "object_repr" varchar(200) NOT NULL, "detail" text NOT NULL, "ip" varchar(45) NOT NULL, "created_at" datetime NOT NULL, "user_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "portal_password_reset_code" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "code_hash" varchar(128) NOT NULL, "created_at" datetime NOT NULL, "expires_at" datetime NOT NULL, "attempts" integer unsigned NOT NULL CHECK ("attempts" >= 0), "max_attempts" integer unsigned NOT NULL CHECK ("max_attempts" >= 0), "used_at" datetime NULL, "user_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED, "last_sent_at" datetime NOT NULL);

CREATE TABLE "rol" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "code" varchar(8) NOT NULL UNIQUE, "name" varchar(50) NOT NULL, "description" text NOT NULL, "scope" varchar(20) NOT NULL, "status" varchar(10) NOT NULL, "is_system" bool NOT NULL);

CREATE TABLE "rol_permiso" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "module" varchar(30) NOT NULL, "action" varchar(20) NOT NULL, "role_id" bigint NOT NULL REFERENCES "rol" ("id") DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "uniq_role_module_action" UNIQUE ("role_id", "module", "action"));

CREATE TABLE "sub_atencion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "code" varchar(8) NOT NULL UNIQUE, "name" varchar(100) NOT NULL, "status" varchar(10) NOT NULL, "attention_type_id" bigint NOT NULL REFERENCES "tipo_atencion" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "tarea_agenda" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "title" varchar(200) NOT NULL, "description" text NULL, "due_date" date NOT NULL, "status" varchar(50) NOT NULL, "goal_id" bigint NOT NULL REFERENCES "meta" ("id") DEFERRABLE INITIALLY DEFERRED, "assigned_to_id" bigint NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "tipo_atencion" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "code" varchar(8) NOT NULL UNIQUE, "name" varchar(100) NOT NULL, "description" text NOT NULL, "status" varchar(10) NOT NULL);

CREATE TABLE "tubo" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "channel" varchar(12) NOT NULL, "title" varchar(255) NOT NULL, "origin" varchar(3) NOT NULL, "requester" varchar(150) NOT NULL, "territory" varchar(60) NOT NULL, "request_date" date NOT NULL, "due_date" date NULL, "support_area" varchar(100) NOT NULL, "notes" text NOT NULL, "status" varchar(15) NOT NULL, "letter_number" varchar(20) NOT NULL, "contact_phone" varchar(20) NOT NULL, "verification_code" varchar(8) NOT NULL, "proof_image" varchar(255) NULL, "completed_at" datetime NULL, "delegation_id" bigint NOT NULL REFERENCES "delegacion" ("id") DEFERRABLE INITIALLY DEFERRED, "responsible_id" bigint NULL REFERENCES "funcionario" ("id") DEFERRABLE INITIALLY DEFERRED);

CREATE TABLE "vecino" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, "created_at" datetime NOT NULL, "updated_at" datetime NOT NULL, "deleted_at" datetime NULL, "identifier" varchar(20) NOT NULL UNIQUE, "full_name" varchar(150) NOT NULL, "phone" varchar(20) NOT NULL, "email" varchar(254) NOT NULL, "status" varchar(10) NOT NULL);

CREATE INDEX "actividad_item_id_6a5e50a1" ON "actividad" ("item_id");

CREATE INDEX "actividad_task_id_8b13a907" ON "actividad" ("task_id");

CREATE INDEX "atencion_attention_subtype_id_76c26728" ON "atencion" ("attention_subtype_id");

CREATE INDEX "atencion_attention_type_id_b643adf7" ON "atencion" ("attention_type_id");

CREATE INDEX "atencion_delegation_id_aa628879" ON "atencion" ("delegation_id");

CREATE INDEX "atencion_neighbor_id_6e3905c3" ON "atencion" ("neighbor_id");

CREATE INDEX "atencion_responsible_id_e88917a9" ON "atencion" ("responsible_id");

CREATE INDEX "auth_group_permissions_group_id_b120cbf9" ON "auth_group_permissions" ("group_id");

CREATE UNIQUE INDEX "auth_group_permissions_group_id_permission_id_0cd325b0_uniq" ON "auth_group_permissions" ("group_id", "permission_id");

CREATE INDEX "auth_group_permissions_permission_id_84c5c92e" ON "auth_group_permissions" ("permission_id");

CREATE INDEX "auth_permission_content_type_id_2f476e4b" ON "auth_permission" ("content_type_id");

CREATE UNIQUE INDEX "auth_permission_content_type_id_codename_01ab375a_uniq" ON "auth_permission" ("content_type_id", "codename");

CREATE INDEX "auth_user_groups_group_id_97559544" ON "auth_user_groups" ("group_id");

CREATE INDEX "auth_user_groups_user_id_6a12ed8b" ON "auth_user_groups" ("user_id");

CREATE UNIQUE INDEX "auth_user_groups_user_id_group_id_94350c0c_uniq" ON "auth_user_groups" ("user_id", "group_id");

CREATE INDEX "auth_user_user_permissions_permission_id_1fbb5f2c" ON "auth_user_user_permissions" ("permission_id");

CREATE INDEX "auth_user_user_permissions_user_id_a95ead1b" ON "auth_user_user_permissions" ("user_id");

CREATE UNIQUE INDEX "auth_user_user_permissions_user_id_permission_id_14a6b632_uniq" ON "auth_user_user_permissions" ("user_id", "permission_id");

CREATE INDEX "beneficio_delivery_area_id_a9db6d9a" ON "beneficio" ("delivery_area_id");

CREATE INDEX "beneficio_employee_id_978e6645" ON "beneficio" ("employee_id");

CREATE INDEX "cierre_semanal_closed_by_id_8774da0f" ON "cierre_semanal" ("closed_by_id");

CREATE INDEX "cierre_semanal_delegation_id_7d8e0e90" ON "cierre_semanal" ("delegation_id");

CREATE INDEX "cumplimiento_goal_id_b90ef6f4" ON "cumplimiento" ("goal_id");

CREATE INDEX "derivacion_tarea_original_employee_id_87aeea83" ON "derivacion_tarea" ("original_employee_id");

CREATE INDEX "derivacion_tarea_reassigned_employee_id_7405698c" ON "derivacion_tarea" ("reassigned_employee_id");

CREATE INDEX "derivacion_tarea_task_id_a159dc73" ON "derivacion_tarea" ("task_id");

CREATE INDEX "dia_libre_funcionario_employee_id_d6d19c20" ON "dia_libre_funcionario" ("employee_id");

CREATE INDEX "dia_libre_funcionario_registered_by_id_9608f6f8" ON "dia_libre_funcionario" ("registered_by_id");

CREATE INDEX "django_admin_log_content_type_id_c4bce8eb" ON "django_admin_log" ("content_type_id");

CREATE INDEX "django_admin_log_user_id_c564eba6" ON "django_admin_log" ("user_id");

CREATE UNIQUE INDEX "django_content_type_app_label_model_76bd3d3b_uniq" ON "django_content_type" ("app_label", "model");

CREATE INDEX "django_session_expire_date_a5c62663" ON "django_session" ("expire_date");

CREATE INDEX "evidencia_activity_id_89f5ea28" ON "evidencia" ("activity_id");

CREATE INDEX "evidencia_validated_by_id_71764cae" ON "evidencia" ("validated_by_id");

CREATE INDEX "felicitacion_reclamo_employee_id_4901cd1e" ON "felicitacion_reclamo" ("employee_id");

CREATE INDEX "felicitacion_reclamo_registered_by_id_05b8fb1d" ON "felicitacion_reclamo" ("registered_by_id");

CREATE INDEX "funcionario_authorized_delegations_delegation_id_0ae7c61e" ON "funcionario_authorized_delegations" ("delegation_id");

CREATE UNIQUE INDEX "funcionario_authorized_delegations_employee_id_delegation_id_9d0caf0d_uniq" ON "funcionario_authorized_delegations" ("employee_id", "delegation_id");

CREATE INDEX "funcionario_authorized_delegations_employee_id_e1c93239" ON "funcionario_authorized_delegations" ("employee_id");

CREATE INDEX "funcionario_delegation_id_edff7af8" ON "funcionario" ("delegation_id");

CREATE INDEX "funcionario_position_id_81baa4b6" ON "funcionario" ("position_id");

CREATE INDEX "funcionario_role_id_636accbb" ON "funcionario" ("role_id");

CREATE INDEX "gestion_atencion_attention_id_b2915656" ON "gestion_atencion" ("attention_id");

CREATE INDEX "gestion_atencion_performed_by_id_4f22bfc7" ON "gestion_atencion" ("performed_by_id");

CREATE INDEX "idx_atencion_deleg_fecha" ON "atencion" ("delegation_id", "created_at");

CREATE INDEX "idx_atencion_estado" ON "atencion" ("status");

CREATE INDEX "idx_atencion_responsable" ON "atencion" ("responsible_id");

CREATE INDEX "idx_atencion_tipo_subtipo" ON "atencion" ("attention_type_id", "attention_subtype_id");

CREATE INDEX "idx_auditoria_fecha" ON "portal_audit_log" ("created_at");

CREATE INDEX "idx_auditoria_user_fecha" ON "portal_audit_log" ("user_id", "created_at");

CREATE INDEX "idx_codigo_recup_user_exp" ON "portal_password_reset_code" ("user_id", "expires_at");

CREATE INDEX "idx_tubo_deleg_canal_estado" ON "tubo" ("delegation_id", "channel", "status");

CREATE INDEX "item_medicion_goal_id_25d20500" ON "item_medicion" ("goal_id");

CREATE INDEX "meta_cargo_item_item_id_1c201b20" ON "meta_cargo_item" ("item_id");

CREATE INDEX "meta_cargo_item_period_id_3b066138" ON "meta_cargo_item" ("period_id");

CREATE INDEX "meta_cargo_item_position_id_a1c82eac" ON "meta_cargo_item" ("position_id");

CREATE INDEX "meta_delegation_id_5bb53cea" ON "meta" ("delegation_id");

CREATE INDEX "meta_period_id_823091bc" ON "meta" ("period_id");

CREATE INDEX "organizacion_comunitaria_delegation_id_479ebe48" ON "organizacion_comunitaria" ("delegation_id");

CREATE INDEX "organizacion_comunitaria_registry_number_72301fa5" ON "organizacion_comunitaria" ("registry_number");

CREATE INDEX "portal_audit_log_user_id_c18cb18d" ON "portal_audit_log" ("user_id");

CREATE INDEX "portal_password_reset_code_user_id_251c9b0b" ON "portal_password_reset_code" ("user_id");

CREATE INDEX "rol_permiso_role_id_9f139892" ON "rol_permiso" ("role_id");

CREATE INDEX "sub_atencion_attention_type_id_a50c2287" ON "sub_atencion" ("attention_type_id");

CREATE INDEX "tarea_agenda_assigned_to_id_80163cda" ON "tarea_agenda" ("assigned_to_id");

CREATE INDEX "tarea_agenda_goal_id_6872c7cb" ON "tarea_agenda" ("goal_id");

CREATE INDEX "tubo_delegation_id_adac8c10" ON "tubo" ("delegation_id");

CREATE INDEX "tubo_responsible_id_b0fc988a" ON "tubo" ("responsible_id");

