# SGR Municipalidad de La Serena — Backend

Backend del **Sistema de Gestión de Resultados (SGR)** para la Municipalidad de
La Serena. Construido con **Django 5.2** sobre Python 3.11.

> **Estado:** proyecto en fase inicial. Actualmente cuenta con modelos,
> migraciones y panel de administración.

---

## Stack tecnológico

| Componente   | Tecnología                     |
|--------------|--------------------------------|
| Lenguaje     | Python 3.11                    |
| Framework    | Django 5.2.17                  |
| Base de datos| SQLite (desarrollo), Postgres disponible vía `psycopg2` |
| Variables de entorno | `python-dotenv` (archivo `.env`) |

## 📁 Estructura del proyecto

```
.
├── config/          # Configuración global (settings, urls, wsgi/asgi)
├── mockup/          # Prototipo / Mockup funcional interactivo (HTML/CSS/JS)
├── rrhh/            # Recursos Humanos: roles, permisos, funcionarios,
│                    #   comunicaciones, reconocimientos, auditoría
├── sgr_core/        # Gestión de resultados: periodos, metas institucionales,
│                    #   cumplimiento e items de medición
├── operaciones/     # Compromisos, actividades, evidencias y atención social
├── manage.py
├── requirements.txt # Dependencias del proyecto
└── .env.example     # Plantilla de variables de entorno (copiar a .env)
```

### 🗂️ Modelos principales

- **rrhh**: `Rol`, `Permiso`, `RolPermiso`, `Cargo`, `Delegacion`, `Funcionario`,
  `Auditoria`, `Notificacion`, `Comunicacion`, `Reconocimiento`
- **sgr_core**: `Delegacion`, `Periodo`, `MetaInstitucional`, `Cumplimiento`, `ItemMedicion`
- **operaciones**: `Compromiso`, `Actividad`, `Evidencia`, `AtencionSocial`

---

## 🎨 Prototipo / Mockup Funcional (Frontend)

Para la evaluación de Análisis y Diseño de Software, el repositorio incluye el prototipo funcional interactivo en la carpeta `mockup/`:

- **Contenido:** 20 vistas de gestión territorial, 13 formularios modales y 6 alertas de excepción del sistema.
- **Ejecución:** No requiere dependencias de servidor ni base de datos. Para probarlo, abrir el archivo `mockup/index.html` en cualquier navegador web moderno (doble clic sobre el archivo).

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
venv\Scriptsctivate            # Windows
# source venv/bin/activate       # Linux/macOS

# Instalar dependencias
pip install -r requirements.txt
```

> **Importante:** en este repositorio conviven dos carpetas: `venv` (el entorno
> **real**, con Django instalado) y `.venv` (vacío, sin paquetes). Usa siempre
> `venv`. Si tu terminal muestra `(.venv)`, actívala con `venv\Scriptsctivate`.

### 3. Configurar el entorno (`.env`)

```bash
cp .env.example .env     # Windows PowerShell:  Copy-Item .env.example .env
```

En el `.env define una clave secreta segura. Para generarla:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Ejemplo de `.env`:

```
DJANGO_SECRET_KEY='tu-clave-secreta-generada'
```

> **Seguridad:** la `SECRET_KEY` **nunca** debe hardcodearse en el código ni
> subirse a git. El archivo .env está excluido por `.gitignore`.

### 4. Migraciones y superusuario

```bash
python manage.py makemigrations   # si cambiaste modelos
python manage.py migrate          # aplica migraciones (crea las tablas)
python manage.py createsuperuser  # usuario para el panel admin
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
| `python manage.py migrate` | Aplica migraciones |
| `python manage.py shell` | Consola interactiva de Django |
| `python manage.py createsuperuser` | Crea usuario admin |

## Notas de seguridad

- `SECRET_KEY` se lee desde `DJANGO_SECRET_KEY` (variable de entorno / `.env`).
- Las contraseñas de los `Funcionario` se guardan **hasheadas** (pbkdf2) mediante
  `set_password()` / `save()` — nunca en texto plano.
- `db.sqlite3` no se versiona (ver `.gitignore`).
- Para producción: `DEBUG=False`, `ALLOWED_HOSTS` con el dominio real, y
  considerar Postgres como base de datos.
