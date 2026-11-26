"""Panel de gestión: ritmo del período y gráficos (preview "Inicio y Ritmo").

- Ritmo: día hábil actual del trimestre, avance real frente al esperado,
  semáforo y ritmo sugerido (registros por día hábil para cerrar al 100 %).
  Es personal si el usuario es un funcionario evaluado; si no, del equipo
  visible (delegación activa).
- Gráficos (HU-17): curva acumulada real vs. esperada, cumplimiento por ítem y
  estado de los tubos. Se dibujan en SVG en el servidor (sin librerías externas).
"""

from collections import Counter
from decimal import Decimal

from django.utils import timezone

from operaciones.calculos import (
    TOPE_CUMPLIMIENTO, calcular_cumplimiento, dias_habiles, registros_contados,
    resumen_equipo, semaforo,
)
from operaciones.models import TubeEntry

from . import access
from .period_context import active_delegation_id, active_period, operational_records

#: Máximo de funcionarios para el cálculo del equipo (el panel debe ser rápido).
MAX_EQUIPO = 80
CERO = Decimal("0")


def _empleados(request):
    """(empleados, alcance) del panel: el propio o el equipo visible."""
    from .goals_views import funcionarios_del_alcance

    employee = getattr(request.user, "employee", None)
    active = access.get_active_delegation(request)
    if (
        employee is not None and employee.position_id and employee.position.is_evaluated
        and (active == access.ALL_DELEGATIONS or employee.delegation_id == getattr(active, "pk", None))
    ):
        return [employee], "personal"
    if not access.get_access(request).can("achievements", "view"):
        return [], ""
    equipo = [e for e in funcionarios_del_alcance(request)[:MAX_EQUIPO] if e.position.is_evaluated]
    return equipo, "equipo"


def ritmo_del_periodo(request, hoy=None):
    hoy = hoy or timezone.localdate()
    periodo = active_period(request)
    if periodo is None:
        return None
    empleados, alcance = _empleados(request)
    habiles = dias_habiles(periodo.start_date, periodo.end_date)
    dia_actual = sum(1 for d in habiles if d <= hoy)
    base = {
        "periodo": periodo, "alcance": alcance, "dia_actual": dia_actual,
        "dias_totales": len(habiles), "quedan": max(len(habiles) - dia_actual, 0),
    }
    if not empleados:
        return {**base, "sin_datos": True}
    delegation_id = active_delegation_id(request)
    tubos = operational_records(request)["tubes"]
    cumplimientos = [
        calcular_cumplimiento(e, periodo, hoy, delegation_id=delegation_id, tubos=tubos)
        for e in empleados
    ]
    con_metas = [c for c in cumplimientos if c["items"]]
    if not con_metas:
        return {**base, "sin_datos": True}
    n = Decimal(len(con_metas))
    real = sum(c["porcentaje"] for c in con_metas) / n
    esperado = sum(c["esperado"] for c in con_metas) / n
    pendiente = CERO
    for c in con_metas:
        for it in c["items"]:
            if it["es_tubo"]:
                continue
            pendiente += max(Decimal(it["meta"]) - Decimal(it["logrado"] or 0), CERO)
    ritmo = (pendiente / base["quedan"]).quantize(Decimal("0.01")) if base["quedan"] else None
    return {
        **base,
        "sin_datos": False,
        "real_pct": real.quantize(Decimal("0.1")),
        "esperado_pct": (esperado * 100).quantize(Decimal("0.1")),
        "semaforo": semaforo(real / 100, esperado),
        "pendiente": pendiente.quantize(Decimal("0.1")),
        "ritmo_sugerido": ritmo,
        "barra_real": min(real, Decimal("100")).quantize(Decimal("0.1")),
        "barra_esperada": min(esperado * 100, Decimal("100")).quantize(Decimal("0.1")),
        "cumplimientos": cumplimientos,
        "empleados": empleados,
    }


def kpis(request, periodo):
    """Cifras del panel: atenciones, tubos activos, prioritarios."""
    from operaciones.periodos import ATENCION_ABIERTA, TUBO_ABIERTO

    info = access.get_access(request)
    datos = {"atenciones": None, "tubos_activos": None, "prioritarios": 0, "sin_registros": True}
    records = operational_records(request)
    if periodo is not None and info.can("attentions", "view"):
        atenciones = records["attentions"]
        datos["atenciones"] = atenciones.count()
        datos["sin_registros"] = not datos["atenciones"]
        datos["prioritarios"] += atenciones.filter(priority=True, status__in=ATENCION_ABIERTA).count()
    if info.can("achievements", "view"):
        tubos = records["tubes"]
        datos["tubos_activos"] = tubos.filter(status__in=TUBO_ABIERTO).count()
        datos["prioritarios"] += tubos.filter(priority=True, status__in=TUBO_ABIERTO).count()
        datos["sin_registros"] = datos["sin_registros"] and not tubos.exists()
    return datos


# ---------------------------------------------------------------------------
# Gráficos (SVG)
# ---------------------------------------------------------------------------

ANCHO, ALTO, MARGEN = 640, 240, 32


def _puntos(valores, total, maximo):
    """Coordenadas "x,y" de una serie (0..maximo) sobre ``total`` puntos."""
    if not valores:
        return ""
    ancho_util, alto_util = ANCHO - 2 * MARGEN, ALTO - 2 * MARGEN
    pasos = max(total - 1, 1)
    puntos = []
    for i, valor in enumerate(valores):
        x = MARGEN + ancho_util * i / pasos
        y = ALTO - MARGEN - alto_util * min(float(valor), maximo) / maximo
        puntos.append(f"{x:.1f},{y:.1f}")
    return " ".join(puntos)


def serie_ritmo(empleados, periodo, hoy, cumplimientos=None, *, delegation_id=None):
    """Curva acumulada real vs. esperada (% de la meta total del trimestre).

    ``cumplimientos`` (opcional) reutiliza los ya calculados para el ritmo.
    """
    habiles = dias_habiles(periodo.start_date, periodo.end_date)
    if not habiles or not empleados:
        return None
    if cumplimientos is None:
        cumplimientos = [
            calcular_cumplimiento(emp, periodo, hoy, delegation_id=delegation_id)
            for emp in empleados
        ]
    meta_total, por_dia = CERO, Counter()
    for emp, c in zip(empleados, cumplimientos):
        items_meta = {it["item"].pk for it in c["items"] if not it["es_tubo"]}
        meta_total += sum((Decimal(it["meta"]) for it in c["items"] if not it["es_tubo"]), CERO)
        for dia, item_id in registros_contados(emp, periodo, delegation_id=delegation_id):
            if item_id in items_meta:
                por_dia[dia] += 1
    if meta_total <= 0:
        return None
    real, esperado, acumulado = [], [], 0
    for i, dia in enumerate(habiles, start=1):
        esperado.append(Decimal(i) / Decimal(len(habiles)) * 100)
        if dia <= hoy:
            acumulado += por_dia.get(dia, 0)
            real.append(Decimal(acumulado) / meta_total * 100)
    maximo = float(max([Decimal(100)] + real))
    return {
        "ancho": ANCHO, "alto": ALTO, "margen": MARGEN,
        "puntos_real": _puntos(real, len(habiles), maximo),
        "puntos_esperado": _puntos(esperado, len(habiles), maximo),
        "real_final": (real[-1] if real else CERO).quantize(Decimal("0.1")),
        "maximo": round(maximo),
        "y_100": ALTO - MARGEN - (ALTO - 2 * MARGEN) * 100 / maximo,
    }


def barras_items(ritmo):
    """Logro por ítem (propio o promedio del equipo), con tope del 120 %."""
    if not ritmo or ritmo.get("sin_datos"):
        return []
    if ritmo["alcance"] == "personal":
        items = [
            {"nombre": it["item"].name, "pct": (min(it["razon"], TOPE_CUMPLIMIENTO) * 100).quantize(Decimal("0.1"))}
            for it in ritmo["cumplimientos"][0]["items"]
        ]
    else:
        filas = [{"empleado": e, "cumplimiento": c} for e, c in zip(ritmo["empleados"], ritmo["cumplimientos"])]
        equipo = resumen_equipo(filas)
        items = [{"nombre": it["item"].name, "pct": it["logro_pct"]} for it in (equipo or {}).get("items_a_reforzar", [])]
    for it in items:
        it["ancho"] = float(min(it["pct"], Decimal("120"))) / 120 * 100
    return sorted(items, key=lambda x: x["pct"])


def estado_tubos(request):
    if not access.get_access(request).can("achievements", "view"):
        return []
    conteo = Counter(operational_records(request)["tubes"].values_list("status", flat=True))
    if not conteo:
        return []
    total = sum(conteo.values())
    return [
        {"etiqueta": etiqueta, "valor": conteo.get(valor, 0), "ancho": conteo.get(valor, 0) * 100 / total,
         "css": valor}
        for valor, etiqueta in TubeEntry.Status.choices
    ]

