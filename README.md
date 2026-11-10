# SGR Municipalidad de La Serena — Backend

Backend del **Sistema de Gestión de Resultados (SGR)** para la Municipalidad de La Serena.
Construido con **Django 5.2** sobre **Python 3.11+**.

> **Estado:** backend operativo. Incluye acceso y recuperación de contraseña, el panel
> de administración de Django (`/admin/`) con scoping por delegación, el portal con
> template común y los 6 mantenedores (Delegaciones, Roles, Usuarios, Ítems y metas,
> Tipo de Atención y Sub Atención) más el módulo de **Atenciones** (ingreso, listado,
> consulta, edición y exportación), con 4 roles y autorización validada en el servidor.
> Incluye **tiempo real** con WebSockets (Django Channels + Daphne): chat por delegación
> y avisos en vivo de nuevas atenciones. La suite de pruebas cubre esquema, autorización,
> autenticación, matriz de permisos, alcance por delegación, las vistas del portal y los
> consumers de tiempo real (ver `docs/pruebas/`).

---

## Stack tecnológico

| Componente   | Tecnología                     |
|--------------|--------------------------------|
| Lenguaje     | Python 3.11 o superior (el entorno de desarrollo actual usa Python 3.14.7) |
| Framework    | Django 5.2.x (`requirements.txt`: `Django==5.2.17`) |
| Tiempo real  | Django Channels 4.x + Daphne 4.x (WebSockets); `CHANNEL_LAYERS` con `InMemoryChannelLayer` |
| Base de datos| MariaDB/MySQL en producción y SQLite por defecto en desarrollo, configurada vía `.env` (`DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`) y construida en `config/settings.py`. El diseño relacional de referencia está en `database/legacy/sgr_municipalidad_laserena_mysql.sql` (MySQL 8, **solo histórico**, ya no refleja el sistema); el driver `mysqlclient` está en `requirements.txt` |
| Variables de entorno | `python-dotenv` (archivo `.env`) |

## 📁 Estructura del proyecto

```
.
├── config/          # Configuración global (settings, urls, wsgi/asgi con Channels)
├── database/        # SQL de referencia (legacy histórico + schema MariaDB)
│   └── legacy/      # Diseño SQL inicial (ya no refleja el sistema; ver LEEME.md)
├── docs/            # Documentación generada (modelo entidad-relación, diseño)
├── deploy/          # Plantilla systemd (sgr.service) para producción EC2
├── sgr_core/        # Dominio: delegaciones, roles, permisos y catálogos
├── operaciones/     # Funcionarios, atenciones, tareas y datos demo (seed_demo)
├── portal/          # Portal web: login, recuperación, inicio, autorización, consumers/routing (WebSockets)
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

## 🌐 Portal web (`portal/`)

El portal implementa el flujo de acceso real (ya no hay mockup en el repositorio):

- **Autenticación** (`portal/backends.py`): usuario o correo, sin distinguir mayúsculas; bloqueo de 5 intentos fallidos por 10 minutos (`portal/views.py`).
- **Recuperación de contraseña** en 3 pasos (`recuperar/`, `recuperar/verificar/`, `recuperar/nueva-clave/`) con código de un solo uso de 10 minutos, hasheado y con reenvío limitado a 45 s.
- **Inicio** (`inicio/`): cifras, accesos por perfil y selector de delegación activa (validado en el servidor).
- **Autorización centralizada** (`portal/access.py`): roles por alcance (todo / autorizadas / su delegación / registros propios), resueltos una sola vez por request.
- **Módulos** (Partes 4 a 7, operativos): Delegaciones, Roles, Usuarios, Ítems y metas,
  Tipo de Atención, Sub Atención y Atenciones. Cada uno con listado, búsqueda, filtro,
  paginación, crear/ver/editar/eliminar (según el rol) y exportación a Excel, con
  autorización validada en el servidor (`portal/access.py` + `portal/crud/`).
- **Páginas de error** propias (403/404/500) definidas en `config/urls.py`.
- **Tiempo real (WebSockets)** (`config/asgi.py`, `portal/routing.py`, `portal/consumers.py`):
  chat de la delegación activa (`ws/chat/<delegacion>/`) y avisos en vivo de nuevas
  atenciones (`ws/atenciones/<delegacion>/`). Al crear una atención se emite el evento
  `attention_created` a los grupos `atenciones_<codigo>` y `atenciones_ALL`; el frontend
  muestra un widget de chat colapsable en la cabecera y un toast de aviso (`sgr.js`).

## 🗄️ Scripts SQL de referencia

- `database/legacy/sgr_municipalidad_laserena_mysql.sql` documenta el diseño relacional
  original de MySQL 8 (19 tablas). **Ya no refleja el sistema**: es un entregable de
  análisis histórico y no se ejecuta con `manage.py` (ver `database/legacy/LEEME.md`).
- `database/sgr_laserena_mariadb_schema.sql` se obtiene con `mysqldump` sobre una base
  MariaDB real (no se regenera desde este proyecto).
- El esquema vigente lo definen los modelos Django y sus migraciones (`migrate`).

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
| `DB_PORT`            | Puerto del motor (solo si no es SQLite)                 | `3306`                   |

Para generar una clave secreta:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> **Seguridad:** la `SECRET_KEY` nunca debe hardcodearse ni subirse a git. El archivo `.env` está excluido por `.gitignore`. `config/settings.py` incluye una clave por defecto válida **sólo para desarrollo**: define siempre `DJANGO_SECRET_KEY` en tu `.env`.

#### Cambiar de motor de base de datos

`config/settings.py` arma `DATABASES` leyendo `.env`, así que **no hay que modificar código** para cambiar de motor:

1. Define el motor y sus parámetros en tu `.env` (si no defines `DB_ENGINE`, se usa SQLite):

   ```
   DB_ENGINE=django.db.backends.mysql
   DB_NAME=sgr_municipalidad_laserena
   DB_USER=usuario
   DB_PASSWORD=clave
   DB_HOST=127.0.0.1
   DB_PORT=3306
   ```

2. Instala el driver del motor elegido: `mysqlclient` ya viene en `requirements.txt` (MariaDB/MySQL).

3. Aplica las migraciones: `python manage.py migrate`.

Si defines `DB_NAME` como ruta relativa (por ejemplo `db.sqlite3`), se resuelve dentro del proyecto.

### 4. Migraciones, datos demo y superusuario

```bash
python manage.py check             # verifica la configuración
python manage.py migrate           # crea las tablas en la base de datos
python manage.py seed_demo         # carga datos demo idempotentes (roles, delegaciones, usuarios, atenciones)
python manage.py createsuperuser   # (opcional) usuario para el panel admin
```

> `seed_demo` es **idempotente**: se puede volver a ejecutar sin duplicar datos.
> Crea los 4 roles base, 6 delegaciones, vecinos, tipos/subtipos de atención,
> 14 atenciones de ejemplo y los **usuarios demo de acceso** (ver tabla más abajo).

### 5. Ejecutar

```bash
python manage.py runserver
```

Portal: <http://127.0.0.1:8000/> · Panel de administración: <http://127.0.0.1:8000/admin/>

### Usuarios demo por rol

Clave de todos: **`Demo2026!`**

| Rol | Usuario (correo) | Delegaciones | Notas |
|---|---|---|---|
| Superadministrador | `superadmin@example.test` | Todas | `is_superuser` sin `Employee` (rol virtual) |
| Coordinador (zona 1) | `coordinador@example.test` | DEL01, DEL02, DEL03 | selector de delegación activa |
| Coordinador (zona 2) | `coordinador2@example.test` | DEL04, DEL05, DEL06 | selector de delegación activa |
| Delegado municipal | `delegado@example.test` | DEL01 | delegación fija |
| Delegado municipal | `delegado.mar@example.test` | DEL02 | delegación fija |
| Funcionario | `funcionario@example.test` | DEL01 | solo atenciones propias |
| Funcionario | `funcionario.mar@example.test` | DEL02 | solo atenciones propias |
| Funcionario (inactivo) | `ignacio.vera@example.test` | DEL03 | cuenta desactivada |

También se crean `admin_demo`, `limitado_demo` y `jefatura_centro` (cuentas del Django Admin).

### Mapa de URLs

| URL | Nombre (reverse) | Acceso |
|---|---|---|
| `/` y `/login/` | `login` | público |
| `/logout/` | `logout` | autenticado (POST) |
| `/inicio/` | `home` | autenticado |
| `/delegacion-activa/` | `switch_delegation` | autenticado (POST) |
| `/recuperar/`, `/recuperar/verificar/`, `/recuperar/reenviar/`, `/recuperar/nueva-clave/` | `password_reset_*` | público |
| `/delegaciones/` (+ `nuevo/`, `<pk>/`, `<pk>/editar/`, `<pk>/eliminar/`, `exportar/`) | `delegations` | superadmin |
| `/roles/` (mismas subrutas) | `roles` | superadmin |
| `/usuarios/` (mismas subrutas) | `users` | superadmin, coordinador, delegado |
| `/items/` (mismas subrutas) | `items` | superadmin, coordinador (delegado solo ver/exportar) |
| `/tipos-atencion/` (mismas subrutas) | `attention_types` | superadmin, coordinador |
| `/sub-atenciones/` (mismas subrutas) | `attention_subtypes` | superadmin, coordinador |
| `/atenciones/` (mismas subrutas + `solicitantes/`) | `attentions` | superadmin, coordinador, delegado, funcionario |
| `/admin/` | — | staff |

### Matriz de permisos por rol

✓ = permitido · ✗ = denegado (403 en el servidor). "Ver/crear/editar/exportar" se abrevian V/C/E/X; "Eliminar" solo lo tiene el superadmin.

| Módulo | Superadmin | Coordinador | Delegado | Funcionario |
|---|---|---|---|---|
| Delegaciones | V·C·E·X·Eliminar | ✗ | ✗ | ✗ |
| Roles | V·C·E·X·Eliminar | ✗ | ✗ | ✗ |
| Usuarios | V·C·E·X·Eliminar | V·C·E·X | V·C·E·X | ✗ |
| Ítems y metas | V·C·E·X·Eliminar | V·C·E·X | V·X | ✗ |
| Tipo de Atención | V·C·E·X·Eliminar | V·C·E·X | ✗ | ✗ |
| Sub Atención | V·C·E·X·Eliminar | V·C·E·X | ✗ | ✗ |
| Atenciones | V·C·E·X·Eliminar | V·C·E·X | V·C·E·X | V·C·X |

Reglas de jerarquía (aplicadas en `portal/access.py`):

- Nadie ve, edita ni elimina usuarios de rango igual o superior (superadmin=3, coordinador=2, delegado=1, funcionario=0).
- Nadie asigna un rol de rango igual o superior al suyo.
- Solo el superadmin elimina registros.

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
| `python manage.py runserver` | Levanta el servidor de desarrollo (usa Daphne/ASGI por defecto) |
| `daphne config.asgi:application --bind 127.0.0.1 --port 8000` | Servidor ASGI de producción (WebSockets) |

## Base de datos MariaDB (producción)

Crear la base con conjunto de caracteres completo (tildes, eñes) y
collation que no distingue mayúsculas (las unicidades de códigos y correos
se validan en formularios y se apoyan en esta collation):

```sql
CREATE DATABASE sgr_laserena
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

En `.env` (`DB_ENGINE=django.db.backends.mysql`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT=3306`); `config/settings.py` agrega
`OPTIONS: {'charset': 'utf8mb4'}` automáticamente para ese motor. El esquema
vigente lo definen los modelos Django y sus migraciones (`migrate`); el SQL
`database/sgr_laserena_mariadb_schema.sql` se obtiene con `mysqldump` sobre
una base real (no se regenera desde este proyecto).

## Notas de seguridad

- `SECRET_KEY` se lee desde `DJANGO_SECRET_KEY` (variable de entorno / `.env`); `DEBUG` y `ALLOWED_HOSTS` también vienen del `.env`.
- Las contraseñas de los funcionarios se gestionan con el sistema de autenticación de Django (`Employee.user`), por lo que se almacenan **hasheadas** (pbkdf2), nunca en texto plano.
- `db.sqlite3` no se versiona (ver `.gitignore`).
- Toda acción que modifica datos va por **POST con CSRF**; eliminar, cerrar sesión y cambiar delegación no tienen ruta por GET.
- Los formularios usan autoescape (sin `|safe` sobre contenido no controlado); no hay SQL crudo ni consultas con cursor.
- Cabeceras básicas: `X-Frame-Options` (middleware de clickjacking), `X-Content-Type-Options: nosniff` (`SECURE_CONTENT_TYPE_NOSNIFF=True`) y cookie de sesión `HttpOnly`.
- Las exportaciones a Excel **nunca** incluyen contraseñas ni hashes.
- Para producción: `DEBUG=False`, `ALLOWED_HOSTS` con el dominio real, sustituir la clave por defecto de `settings.py`, configurar `STATIC_ROOT` para `collectstatic` y usar MariaDB/MySQL como base de datos.

## Configuración del correo

El envío del código de recuperación de contraseña usa `django.core.mail` con el
backend configurado en `.env`. Por defecto está **simulado** (imprime el código
en la consola del servidor), pensado para desarrollo y pruebas.

| Variable | Descripción |
|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.console.EmailBackend` (simulado, por defecto) o `django.core.mail.backends.smtp.EmailBackend` (real) |
| `EMAIL_HOST` / `EMAIL_PORT` | Servidor SMTP y puerto (p. ej. `smtp.gmail.com` / `587`) |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Credenciales SMTP |
| `EMAIL_USE_TLS` | `True` para TLS |
| `DEFAULT_FROM_EMAIL` | Remitente de los correos |

En modo simulado, el código de 6 dígitos aparece en el log del servicio:

```bash
sudo journalctl -u sgr -n 50 --no-pager   # busca la línea con el "Código de recuperación"
```

## Estado por módulo (honesto)

| Módulo | Estado |
|---|---|
| Autenticación (login, bloqueo de intentos) | Operativo |
| Recuperación de contraseña (3 pasos) | Operativo (correo **simulado** por consola si no hay SMTP) |
| Inicio (cifras, accesos, selector de delegación) | Operativo |
| Delegaciones | Operativo |
| Roles | Operativo |
| Usuarios | Operativo |
| Ítems y metas | Operativo |
| Tipo de Atención | Operativo |
| Sub Atención | Operativo |
| Atenciones (ingreso, listado, consulta, edición, exportación) | Operativo |
| Matriz de permisos y alcance por delegación | Operativo (validado en servidor) |
| Envío de correo con SMTP real | Simulado (backend de consola hasta configurar SMTP) |
| Pruebas de estrés (Locust) | Operativo / **Ejecutado** (ver `docs/pruebas/pruebas_estres.md`) |
| Tiempo real (chat y atenciones en vivo) | Operativo (Channels + Daphne, `InMemoryChannelLayer`) |
| Logo y tipografía oficiales | Operativo (paleta granate #920000, tipografía sin serifas y escudo/imagotipo institucional en `base.html` y `base_auth.html`) |

---

## Despliegue en producción (EC2)

> ⚠️ **En producción, `DEBUG` debe ser `False` y `ALLOWED_HOSTS` debe incluir la IP pública real de la instancia** (o su dominio). Nunca despliegues con `DEBUG=True`.

1. **Instalar dependencias** (en la instancia, con el venv activado):

   ```bash
   pip install -r requirements.txt
   ```

2. **Configurar `.env` de producción** (copia `.env.example` a `.env` y ajusta):

   ```bash
   cp .env.example .env
   ```

   Define al menos: `DJANGO_SECRET_KEY` (genera una nueva), `DEBUG=False`, `ALLOWED_HOSTS=<IP_PUBLICA_REAL>` y las variables `DB_*` de MariaDB (`DB_ENGINE=django.db.backends.mysql`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT=3306`).

3. **Recolectar estáticos, migrar y cargar datos demo**:

   ```bash
   python manage.py collectstatic --noinput
   python manage.py migrate
   python manage.py seed_demo        # solo si se quieren datos de demostración
   ```

4. **Levantar el servicio con systemd** (usa la plantilla `deploy/sgr.service`; reemplaza `<RUTA_PROYECTO>` y `<USUARIO>` con los valores reales de la instancia):

   ```bash
   sudo cp deploy/sgr.service /etc/systemd/system/sgr.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now sgr
   sudo systemctl status sgr
   ```

   El servicio corre `daphne config.asgi:application` (servidor ASGI, necesario para los
   WebSockets de tiempo real) para que el proceso siga vivo al cerrar la sesión SSH.

   > ⚠️ **Tiempo real y escalado:** el `CHANNEL_LAYERS` actual usa `InMemoryChannelLayer`,
   > válido para un **único proceso** de Daphne. Para escalar a varios workers/instancias,
   > configura `channels_redis` y apunta `CHANNEL_LAYERS` a Redis.
