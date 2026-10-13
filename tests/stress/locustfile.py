"""Escenarios Locust para el SGR (pruebas de estrés de cierre).

Solo para instancias de PRUEBAS, nunca AWS de producción. Los umbrales de
referencia están en ``docs/pruebas/pruebas_estres.md``.

Uso:
    cd tests/stress
    LOCUST_USER=funcionario LOCUST_PASSWORD=Demo2026! \
        locust -f locustfile.py --host http://<INSTANCIA>:8000
"""

import os

from locust import HttpUser, between, task


USER = os.getenv("LOCUST_USER", "funcionario")
PASSWORD = os.getenv("LOCUST_PASSWORD", "Demo2026!")


def _csrf(client, path):
    """Token CSRF del formulario de una página (para los POST)."""
    resp = client.get(path)
    resp.raise_for_status()
    marker = 'name="csrfmiddlewaretoken" value="'
    i = resp.text.find(marker)
    if i == -1:
        return ""
    i += len(marker)
    return resp.text[i: resp.text.find('"', i)]


class PortalUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.verify = False
        token = _csrf(self.client, "/login/")
        if token:
            resp = self.client.post("/login/", {
                "csrfmiddlewaretoken": token,
                "username": USER,
                "password": PASSWORD,
            })
            resp.raise_for_status()

    @task(3)
    def listado_busqueda(self):
        self.client.get("/atenciones/?q=social", name="/atenciones/?q=")

    @task(2)
    def listado_paginado(self):
        self.client.get("/atenciones/?page=2", name="/atenciones/?page=")

    @task(2)
    def ingreso_atencion_form(self):
        self.client.get("/atenciones/nuevo/", name="/atenciones/nuevo/")

    @task(1)
    def exportacion(self):
        self.client.get("/atenciones/exportar/", name="/atenciones/exportar/")
