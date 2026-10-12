# Pruebas funcionales y de estrés

## 1. Pruebas automáticas (Django)

```bash
python manage.py test
```

Se ejecutan sobre una base de datos temporal; no tocan tus datos. Cubren:

| App | Qué comprueba |
|---|---|
| `catalogos` | Modelos Tipo de Atención / Sub Atención (únicos, `__str__`); CRUD en el admin (crear, editar, listar, buscar, borrar); duplicados sin distinguir mayúsculas; no se borra un tipo con sub atenciones; usuario sin permisos recibe 403. |
| `sgr_core` | CRUD de Metas e Ítems en el admin; ponderación 0–100 y suma ≤ 100 % por período y delegación; valores negativos rechazados; ítem duplicado en una meta; porcentaje de cumplimiento 0–100. |
| `portal` | Login correcto/incorrecto; el dashboard exige sesión; flujo completo de recuperación de contraseña (correo enviado, enlace de un solo uso, contraseña débil rechazada, correo inexistente no revela nada, usuario inactivo no recibe correo). |
| `operaciones` | `seed_demo` idempotente y con catálogos; *scoping* por rol (superusuario ve todo, jefatura solo su delegación, usuario solo sus tareas). |

Resultado esperado: `OK` al final (38 pruebas).

## 2. Pruebas funcionales manuales (checklist)

Cargar datos: `python manage.py seed_demo`. Anotar ✔/✘ y adjuntar captura.

| # | Caso | Pasos | Resultado esperado | ✔/✘ |
|---|---|---|---|---|
| F1 | Login | `/login/` con `admin_demo` / `Demo2026!` | Entra al dashboard | |
| F2 | Login inválido | Clave incorrecta | Mensaje de error, no entra | |
| F3 | Crear Tipo de Atención | Admin → Tipos de Atención → Añadir | Se guarda y aparece en la lista | |
| F4 | Sub Atención dentro del tipo | En el tipo, añadir fila en "Sub atenciones" | Se guarda con el tipo | |
| F5 | Duplicado | Crear otro tipo con el mismo nombre en distinto formato (`social` vs `Social`) | Error "Ya existe…" | |
| F6 | Borrado protegido | Borrar un tipo que tiene sub atenciones | Django lo impide y lista los objetos | |
| F7 | Crear Meta | Admin → Metas Institucionales → Añadir (ponderación 40) | Se guarda | |
| F8 | Ponderación inválida | Meta con ponderación 150 | Error "entre 0 y 100" | |
| F9 | Suma > 100 % | Agregar una meta que haga superar 100 % en la misma delegación y período | Error "sumarían…" | |
| F10 | Ítems en la meta | Abrir una meta → agregar ítem en la tabla de abajo | Se guarda; la lista de metas muestra el nº de ítems | |
| F11 | Ítem inválido | Línea base negativa | Error "no puede ser negativo" | |
| F12 | Búsqueda de ítems | Ítems de Medición → buscar "operativos" | Filtra resultados | |
| F13 | Recuperación de contraseña | `/login/` → "¿Olvidó su contraseña?" → correo de `jefatura_centro` | Llega el correo; el enlace permite cambiar la clave | |
| F14 | Enlace usado | Abrir de nuevo el mismo enlace | "El enlace no es válido o ya venció" | |
| F15 | Permisos | Entrar como `jefatura_centro` → `/admin/catalogos/attentiontype/` | 403 (solo admin gestiona catálogos) | |

## 3. Prueba de estrés (Locust)

El script `tests/stress/locustfile.py` simula dos tipos de usuario (funcionarios en el
portal y administradores navegando/buscando en el admin). Solo hace lecturas e inicios de sesión.

```bash
pip install -r requirements-dev.txt          # solo en el PC que genera la carga

# Con interfaz web: abrir http://localhost:8089 e indicar usuarios y velocidad de subida
locust -f tests/stress/locustfile.py --host http://<IP_PUBLICA>

# Sin interfaz (50 usuarios, +5 por segundo, 2 minutos) con reportes
mkdir resultados
locust -f tests/stress/locustfile.py --host http://<IP_PUBLICA> --headless \
       -u 50 -r 5 -t 2m --csv resultados/estres --html resultados/estres.html
```

Recomendación: partir con 10 usuarios y subir (10 → 25 → 50 → 100) hasta ver degradación.
Requiere haber ejecutado `seed_demo` en el servidor probado. Lanzar la carga contra tu propia
instancia, **no contra servidores de terceros**.

**Cómo leer el resultado:** `Failures` debe ser 0 %; mirar la mediana (50 %) y el percentil 95;
anotar a cuántos usuarios simultáneos empiezan a aparecer fallos o tiempos > 2 s.

### Resultado de referencia (entorno de desarrollo, no es EC2)

Prueba corrida al construir esto: gunicorn con 3 *workers*, SQLite, 30 usuarios, 40 s, equipo de
desarrollo con CPU limitada: **464 peticiones, 0 fallos**; mediana **16 ms**, p95 ≈ 4,3 s.
Las páginas normales respondieron en decenas de milisegundos; los tiempos altos fueron casi
solo los **inicios de sesión** (≈ 4 s con 30 logins a la vez), porque Django verifica la
contraseña con PBKDF2, que gasta CPU a propósito. Es esperable y es el cuello de botella a
vigilar en EC2 (`t3.micro` tiene poca CPU): conviene subir los *workers* de gunicorn solo si hay más núcleos.

### Resultados en EC2 (completar)

| Fecha | Instancia | Usuarios | Duración | Peticiones | Fallos | Mediana | p95 | Observación |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |
