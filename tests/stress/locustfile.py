"""Prueba de estrés del SGR con Locust.

Instalación (solo en el equipo que genera la carga, NO en producción):
    pip install -r requirements-dev.txt

Ejecución con interfaz web (http://localhost:8089):
    locust -f tests/stress/locustfile.py --host http://<IP_O_DOMINIO>

Ejecución sin interfaz (ej. 50 usuarios, 2 min) y reporte CSV/HTML:
    locust -f tests/stress/locustfile.py --host http://<IP_O_DOMINIO> \
           --headless -u 50 -r 5 -t 2m --csv resultados/estres --html resultados/estres.html

Usa los usuarios de `python manage.py seed_demo` (clave Demo2026!).
Solo hace lecturas (GET) y inicios de sesión: no crea ni borra datos.
"""
import random

from locust import HttpUser, between, task

PASSWORD = "Demo2026!"


def _login(client, url, username):
    """Inicia sesión manejando el token CSRF de Django."""
    client.get(url, name=f"GET {url}")
    token = client.cookies.get("csrftoken", "")
    with client.post(
        url,
        data={"username": username, "password": PASSWORD, "csrfmiddlewaretoken": token},
        headers={"Referer": client.base_url + url},
        name=f"POST {url}",
        catch_response=True,
    ) as resp:
        # Un login correcto redirige (302 -> ya seguido) y deja la cookie de sesión
        if "sessionid" not in client.cookies:
            resp.failure("No se inició sesión (revise usuario/clave o seed_demo)")


class PortalUser(HttpUser):
    """Funcionario que entra al portal y revisa su panel."""
    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        _login(self.client, "/login/", random.choice(["jefatura_centro", "limitado_demo", "diego.molina"]))

    @task(5)
    def dashboard(self):
        self.client.get("/dashboard/", name="GET /dashboard/")

    @task(1)
    def pagina_recuperacion(self):
        self.client.get("/password-reset/", name="GET /password-reset/")


class AdminUser(HttpUser):
    """Administrador que navega y busca en los CRUD del panel."""
    weight = 2
    wait_time = between(1, 4)

    def on_start(self):
        _login(self.client, "/admin/login/?next=/admin/", "admin_demo")

    @task(3)
    def indice(self):
        self.client.get("/admin/", name="GET /admin/")

    @task(4)
    def listas(self):
        url = random.choice([
            "/admin/sgr_core/institutionalgoal/",
            "/admin/sgr_core/measurementitem/",
            "/admin/catalogos/attentiontype/",
            "/admin/catalogos/attentionsubtype/",
            "/admin/operaciones/task/",
            "/admin/operaciones/employee/",
        ])
        self.client.get(url, name="GET lista admin")

    @task(2)
    def busquedas(self):
        q = random.choice([
            "/admin/sgr_core/measurementitem/?q=operativos",
            "/admin/sgr_core/institutionalgoal/?q=Centro",
            "/admin/catalogos/attentionsubtype/?q=visita",
            "/admin/operaciones/employee/?q=diego",
        ])
        self.client.get(q, name="GET búsqueda admin")

    @task(1)
    def formulario_nuevo(self):
        self.client.get("/admin/catalogos/attentiontype/add/", name="GET formulario nuevo")
