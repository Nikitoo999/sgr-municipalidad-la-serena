# Pruebas de estrés (Locust)

> ⚠️ **No ejecutar contra el servidor de AWS de producción.** Estas pruebas
> generan carga artificial. Ejecútalas **solo** contra la instancia de pruebas
> (o un entorno local) y en una **ventana acordada** con el equipo, para no
> alterar las métricas ni el servicio real.

## Objetivo

Verificar que los flujos principales del portal (login, listado con búsqueda y
paginación, ingreso de atención y exportación) responden de forma aceptable bajo
carga concurrente, dentro de los límites de una instancia micro de EC2.

## Requisitos

```bash
pip install -r requirements-dev.txt   # agrega locust
```

Se necesita una instancia con datos demo cargados (`python manage.py seed_demo`).

## Umbrales definidos ANTES de ejecutar

Estos umbrales son la referencia contra la que se comparará el resultado; no se
modifican después de correr la prueba.

| Métrica | Umbral |
|---|---|
| Usuarios simultáneos (pico) | 50 |
| Tasa de aparición (spawn rate) | 5 usuarios/s |
| Duración de la prueba | 5 minutos |
| Porcentaje máximo de errores | < 5 % |
| p95 máximo por petición | 2 000 ms |
| p99 máximo por petición | 5 000 ms |

## Escenarios

Definidos en `tests/stress/locustfile.py`:

1. **Login** — `POST /login/` con un usuario demo y lectura del token CSRF.
2. **Listado con búsqueda y paginación** — `GET /atenciones/?q=...&page=...`.
3. **Ingreso de atención** — flujo `GET /atenciones/nuevo/` + `POST /atenciones/nuevo/`.
4. **Exportación** — `GET /atenciones/exportar/`.

## Cómo ejecutar

```bash
cd tests/stress
locust -f locustfile.py --host http://<INSTANCIA_PRUEBAS>:8000
```

Luego abrir la interfaz web de Locust en <http://localhost:8089>, configurar los
umbrales de arriba y lanzar la prueba.

> Los usuarios demo (`superadmin`, `coordinador`, `delegado`, `funcionario`) usan
> la clave `Demo2026!`. Las credenciales se configuran con variables de entorno:
> `LOCUST_USER` y `LOCUST_PASSWORD`.

## Advertencias

- **Una instancia micro de EC2 tiene límites de CPU y memoria** (típicamente
  1 vCPU y 1 GB). Con 50 usuarios concurrentes es esperable que los tiempos suban
  y que algunos requests fallen; los umbrales asumen esta realidad y se comparan
  contra una instancia de pruebas aislada.
- Ejecuta **fuera de horario** o en una **ventana acordada**.
- No uses la exportación masiva como escenario de carga sostenida: genera un
  archivo Excel por request y consume CPU.

## Resultados

| Fecha | Instancia | Usuarios | Duración | % errores | p95 | p99 | ¿Cumple? | Observaciones |
|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |

> La tabla se completa **después** de ejecutar la prueba. No se reportan
> resultados sin haber corrido Locust.
