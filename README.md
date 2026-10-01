# SGR Municipalidad de La Serena — Backend

Backend del **Sistema de Gestión de Resultados (SGR)** para la Municipalidad de La Serena.
Construido con **Django 5.2** sobre **Python 3.11+**.

> **Estado:** proyecto en fase inicial. El backend expone hoy únicamente el panel de
> administración de Django (`/admin/`) sobre los modelos de datos: todavía no hay
> vistas, API ni pruebas propias. Los modelos y sus migraciones iniciales ya están
> creados y aplicados.

---

## Stack tecnológico

| Componente   | Tecnología                     |
|--------------|--------------------------------|
| Lenguaje     | Python 3.11 o superior (el entorno de desarrollo actual usa Python 3.14.7) |
| Framework    | Django 5.2.x (`requirements.txt`: `Django>=5.2,<5.3`; instalado: 5.2.17) |
| Base de datos| SQLite por defecto, configurada vía `.env` (`DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) y construida en `config/settings.py`. El diseño relacional de referencia está en `database/sgr_municipalidad_laserena_mysql.sql` (MySQL 8); `psycopg2-binary` ya está en `requirements.txt` para Postgres |
| Variables de entorno | `python-dotenv` (archivo `.env`) |

## 📁 Estructura del proyecto

```
.
├── config/          # Configuración global (settings, urls, wsgi/asgi)
├── database/        # Script SQL de referencia (diseño relacional)
├── mockup/          # Prototipo funcional interactivo (HTML/CSS/JS, sin backend)
├── sgr_core/        # Gestión de resultados: períodos, metas, cumplimiento e ítems
├── operaciones/     # Tareas, actividades, evidencias y funcionarios
├── manage.py
├── requirements.txt # Dependencias del proyecto
└── .env.example     # Plantilla de variables de entorno (copiar a .env)
```

### 🗂️ Modelos

**sgr_core** (`sgr_core/models.py`)

- `BaseModel` (abstracto): agrega `created_at`, `updated_at` y `deleted_at` al resto de los modelos.
- `Delegation` (tabla `delegacion`): delegación territorial.
- `Period` (tabla `periodo`): período de medición con trimestre y estado.
- `InstitutionalGoal` (tabla `meta`): meta institucional con ponderación, período y delegación.
- `Achievement` (tabla `cumplimiento`): porcentaje de cumplimiento de una meta.
- `MeasurementItem` (tabla `item_medicion`): indicador, unidad de medida, línea base y valor objetivo.

**operaciones** (`operaciones/models.py`)

- `Task` (tabla `tarea_agenda`): tarea comprometida sobre una meta institucional.
- `Activity` (tabla `actividad`): actividad ejecutada dentro de una tarea.
- `Evidence` (tabla `evidencia`): respaldo de una actividad y su validación de jefatura.
- `Employee` (tabla `funcionario`): funcionario municipal. Se enlaza con el usuario de Django (`django.contrib.auth.models.User`) mediante `OneToOneField` e incorpora RUT, teléfono y delegación asignada.

### 🔐 Panel de administración

Los 9 modelos están registrados en el admin de Django con `list_select_related` para
evitar consultas N+1. Además, `TaskAdmin` (`operaciones/admin.py`) aplica *scoping*
por delegación:

- Superusuario: ve todas las tareas.
- Funcionario con `Employee` asociado: sólo las tareas de su delegación.
- Usuario sin `Employee`: no ve ninguna.

### 🗃️ Migraciones

```
├── sgr_core/migrations/0001_initial.py      # Delegation, Period, InstitutionalGoal,
│                                            #   Achievement, MeasurementItem
└── operaciones/migrations/0001_initial.py   # Task, Activity, Evidence, Employee
```

---

## 🎨 Prototipo / Mockup Funcional (Frontend)

Para la evaluación de Análisis y Diseño de Software, el repositorio incluye el prototipo funcional interactivo en `mockup/sgr_mockup.html`:

- **Contenido:** pantalla de acceso + 19 vistas de gestión (de `02_panel_general` a `20_busqueda`), 13 formularios modales (`form_01` a `form_13`) y 6 alertas de excepción (`alerta_01` a `alerta_06`).
- **Ejecución:** no requiere servidor ni base de datos. Abre `mockup/sgr_mockup.html` en cualquier navegador web moderno (doble clic sobre el archivo).
- **Alcance:** es sólo front-end, con datos de ejemplo escritos en el propio HTML; aún no está conectado a Django (no existen vistas ni URLs que lo sirvan).

## 🗄️ Script SQL de referencia

`database/sgr_municipalidad_laserena_mysql.sql` documenta el diseño relacional para
MySQL 8: crea la base `sgr_municipalidad_laserena` con 19 tablas (`role`, `permission`,
`position`, `delegation`, `period`, `social_service`, `role_permission`, `employee`,
`goal`, `achievement`, `metric`, `commitment`, `activity`, `evidence`, `communication`,
`notification`, `recognition`, `report`, `audit_log`).

Consideraciones:

- **No se ejecuta con `manage.py`**: es un entregable de diseño; el esquema real se genera con las migraciones de Django sobre SQLite.
- **No incluye datos de prueba**: sólo contiene la estructura.
- **Nombres distintos**: el script nombra las tablas en inglés, mientras los `db_table` de los modelos están en español (`delegacion`, `periodo`, `meta`, `cumplimiento`, `item_medicion`, `tarea_agenda`, `actividad`, `evidencia`, `funcionario`). Conviene unificar el criterio en una próxima iteración.
- Varias tablas del script todavía no tienen modelo Django: `role`, `permission`, `position`, `role_permission`, `social_service`, `commitment`, `communication`, `notification`, `recognition`, `report`, `audit_log`.

---

## Puesta en marcha

### 1. Requisitos previos

- Python 3.11 o superior
- `git`

### 2. Clonar e instalar

```bash
git clone https://github.com/Nikitoo999/sgr-municipalidad-la-serena.git
cd sgr-municipalidad-la-serena

# Crear y activar el entorno virtual
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux/macOS

# Instalar dependencias
pip install -r requirements.txt
```

> **Entornos virtuales:** `venv/` y `.venv/` están excluidos por `.gitignore`, así que no se versionan. Crea el tuyo en la raíz del proyecto y usa siempre el mismo; comprueba que Django quedó instalado con `python -c "import django; print(django.get_version())"`.

### 3. Configurar el entorno (`.env`)

```bash
cp .env.example .env     # Windows PowerShell:  Copy-Item .env.example .env
```

`config/settings.py` lee estas variables:

| Variable             | Descripción                                             | Ejemplo                  |
|----------------------|---------------------------------------------------------|--------------------------|
| `DJANGO_SECRET_KEY`  | Clave secreta de Django                                 | `tu-clave-secreta`       |
| `DEBUG`              | `True` / `False` (si no se define, se asume `True`)     | `True`                   |
| `ALLOWED_HOSTS`      | Hosts permitidos, separados por coma                    | `localhost,127.0.0.1`    |
| `DB_ENGINE`          | Motor de base de datos (por defecto SQLite)             | `django.db.backends.sqlite3` |
| `DB_NAME`            | Ruta o nombre de la base de datos                       | `db.sqlite3`             |
| `DB_USER`            | Usuario del motor (solo si no es SQLite)                | `usuario`                |
| `DB_PASSWORD`        | Contraseña del motor (solo si no es SQLite)             | `clave`                  |
| `DB_HOST`            | Host del motor (solo si no es SQLite)                   | `127.0.0.1`              |
| `DB_PORT`            | Puerto del motor (solo si no es SQLite)                 | `5432`                   |

Para generar una clave secreta:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> **Seguridad:** la `SECRET_KEY` nunca debe hardcodearse ni subirse a git. El archivo `.env` está excluido por `.gitignore`. `config/settings.py` incluye una clave por defecto válida **sólo para desarrollo**: define siempre `DJANGO_SECRET_KEY` en tu `.env`.

#### Cambiar de motor de base de datos

`config/settings.py` arma `DATABASES` leyendo `.env`, así que **no hay que modificar código** para cambiar de motor:

1. Define el motor y sus parámetros en tu `.env` (si no defines `DB_ENGINE`, se usa SQLite):

   ```
   DB_ENGINE=django.db.backends.postgresql
   DB_NAME=sgr_municipalidad_laserena
   DB_USER=usuario
   DB_PASSWORD=clave
   DB_HOST=127.0.0.1
   DB_PORT=5432
   ```

2. Instala el driver del motor elegido: `psycopg2-binary` ya viene en `requirements.txt` (Postgres); para MySQL 8 se necesita `mysqlclient`, que **no** está en `requirements.txt`.

3. Aplica las migraciones: `python manage.py migrate`.

Si defines `DB_NAME` como ruta relativa (por ejemplo `db.sqlite3`), se resuelve dentro del proyecto.

### 4. Migraciones y superusuario

```bash
python manage.py check             # verifica la configuración
python manage.py migrate           # crea las tablas en la base de datos
python manage.py createsuperuser   # usuario para el panel admin
```

### 5. Ejecutar

```bash
python manage.py runserver
```

Panel de administración: <http://127.0.0.1:8000/admin/>

---

## Comandos útiles

| Comando | Descripción |
|---|---|
| `python manage.py check` | Verifica la configuración sin errores |
| `python manage.py makemigrations --check --dry-run` | Detecta migraciones pendientes |
| `python manage.py makemigrations` | Genera migraciones al cambiar los modelos |
| `python manage.py migrate` | Aplica migraciones |
| `python manage.py shell` | Consola interactiva de Django |
| `python manage.py createsuperuser` | Crea usuario admin |
| `python manage.py runserver` | Levanta el servidor de desarrollo |

## Notas de seguridad

- `SECRET_KEY` se lee desde `DJANGO_SECRET_KEY` (variable de entorno / `.env`).
- Las contraseñas de los funcionarios se gestionan con el sistema de autenticación de Django (`Employee.user`), por lo que se almacenan **hasheadas** (pbkdf2), nunca en texto plano.
- `db.sqlite3` no se versiona (ver `.gitignore`).
- Para producción: `DEBUG=False`, `ALLOWED_HOSTS` con el dominio real, sustituir la clave por defecto de `settings.py`, configurar `STATIC_ROOT` para `collectstatic` y evaluar MySQL/Postgres como base de datos.
