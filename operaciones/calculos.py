"""Cálculos compartidos de la matriz SGR (días hábiles y metas ajustadas)."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from operaciones.models import Activity
from sgr_core.models import PositionItemGoal

CENTESIMOS = Decimal("0.01")


def dias_habiles(desde, hasta):
    """Lista de fechas de lunes a viernes entre dos fechas (inclusive)."""
    fechas, dia = [], desde
    while dia <= hasta:
        if dia.weekday() < 5:
            fechas.append(dia)
        dia += timedelta(days=1)
    return fechas


def dias_libres(employee, period):
    """Días hábiles del trimestre en que el funcionario no trabaja."""
    habiles = set(dias_habiles(period.start_date, period.end_date))
    libres = set()
    registros = employee.days_off.filter(
        deleted_at__isnull=True,
        start_date__lte=period.end_date,
        end_date__gte=period.start_date,
    )
    for registro in registros:
        desde = max(registro.start_date, period.start_date)
        hasta = min(registro.end_date, period.end_date)
        libres |= set(dias_habiles(desde, hasta))
    return libres & habiles


def factor_ajuste(employee, period):
    """Proporción de días hábiles efectivos del trimestre (1 = sin días libres)."""
    total = len(dias_habiles(period.start_date, period.end_date))
    if total == 0:
        return Decimal("1")
    efectivos = total - len(dias_libres(employee, period))
    return Decimal(efectivos) / Decimal(total)


def meta_ajustada(meta, factor):
    """Meta del trimestre descontando los días libres."""
    return (Decimal(meta) * factor).quantize(CENTESIMOS, rounding=ROUND_HALF_UP)


# --- Cumplimiento de la matriz (3.6) ---------------------------------------

#: Tope de cumplimiento por ítem (120 %). Se puede cambiar con SGR_TOPE_CUMPLIMIENTO.
TOPE_CUMPLIMIENTO = Decimal(str(getattr(settings, "SGR_TOPE_CUMPLIMIENTO", "1.20")))
#: Regla del cliente: no se cuentan más de 7 actividades por día y funcionario.
MAX_ACTIVIDADES_POR_DIA = 7
#: Semáforo: amarillo desde el 60 % de lo esperado a la fecha.
UMBRAL_AMARILLO = Decimal("0.60")


def razon_logro(logrado, meta):
    """Logrado / meta. Con meta 0 (ítem sin meta fija, como Emergencia) cumple si hubo algo."""
    meta = Decimal(meta)
    if meta == 0:
        return Decimal("1") if logrado > 0 else Decimal("0")
    return Decimal(logrado) / meta


def puntaje_item(razon, ponderador, tope=None):
    """min(razón, tope) × ponderador, en puntos sobre 100."""
    tope = TOPE_CUMPLIMIENTO if tope is None else tope
    return (min(razon, tope) * Decimal(ponderador)).quantize(CENTESIMOS, rounding=ROUND_HALF_UP)


def semaforo(razon, esperado):
    """Verde si va al día, amarillo si está sobre el 60 % de lo esperado, rojo si no."""
    if esperado <= 0 or razon >= esperado:
        return "verde"
    if razon >= esperado * UMBRAL_AMARILLO:
        return "amarillo"
    return "rojo"


def logrado_por_item(employee, period):
    """Actividades que suman por ítem: realizadas, con evidencia validada, dentro del trimestre.

    Cada día cuenta a lo más MAX_ACTIVIDADES_POR_DIA actividades.
    """
    filas = (
        Activity.objects.filter(
            deleted_at__isnull=True,
            task__deleted_at__isnull=True,
            task__assigned_to=employee,
            item__isnull=False,
            status=Activity.Status.DONE,
            execution_date__range=(period.start_date, period.end_date),
            evidences__is_validated=True,
            evidences__deleted_at__isnull=True,
        )
        .order_by("execution_date", "pk")
        .values_list("pk", "execution_date", "item_id")
        .distinct()
    )
    por_dia, logrado = defaultdict(int), defaultdict(int)
    for _pk, dia, item_id in filas:
        if por_dia[dia] < MAX_ACTIVIDADES_POR_DIA:
            por_dia[dia] += 1
            logrado[item_id] += 1
    return dict(logrado)


def dias_efectivos(employee, period, hasta=None):
    """Días hábiles trabajados (sin días libres) del trimestre, hasta una fecha."""
    limite = min(hasta, period.end_date) if hasta else period.end_date
    if limite < period.start_date:
        return 0
    habiles = set(dias_habiles(period.start_date, limite))
    return len(habiles - dias_libres(employee, period))


def avance_esperado(employee, period, hoy):
    """Fracción del trimestre que debería llevar avanzada a la fecha `hoy`."""
    total = dias_efectivos(employee, period)
    if total == 0:
        return Decimal("1")
    return Decimal(dias_efectivos(employee, period, hoy)) / Decimal(total)


def calcular_cumplimiento(employee, period, hoy=None):
    """Cumplimiento de un funcionario en un trimestre, ítem por ítem."""
    hoy = hoy or date.today()
    resultado = {
        "items": [], "puntaje_total": Decimal("0.00"), "suma_pesos": Decimal("0"),
        "porcentaje": Decimal("0.00"), "esperado": Decimal("0"), "semaforo": "verde",
    }
    if employee.position_id is None:
        return resultado

    metas = (
        PositionItemGoal.objects.filter(
            position_id=employee.position_id, period=period, deleted_at__isnull=True,
        ).select_related("item").order_by("item__code")
    )
    logrado = logrado_por_item(employee, period)
    factor = factor_ajuste(employee, period)
    esperado = avance_esperado(employee, period, hoy)

    total, suma_pesos = Decimal("0"), Decimal("0")
    for goal in metas:
        meta = meta_ajustada(goal.target_value, factor)
        hecho = logrado.get(goal.item_id, 0)
        razon = razon_logro(hecho, meta)
        puntaje = puntaje_item(razon, goal.weight)
        total += puntaje
        suma_pesos += goal.weight
        resultado["items"].append({
            "item": goal.item, "peso": goal.weight, "meta": meta, "logrado": hecho,
            "razon": razon, "puntaje": puntaje, "semaforo": semaforo(razon, esperado),
        })

    razon_global = (total / suma_pesos) if suma_pesos else Decimal("0")
    resultado.update({
        "puntaje_total": total.quantize(CENTESIMOS),
        "suma_pesos": suma_pesos,
        "porcentaje": (razon_global * 100).quantize(CENTESIMOS, rounding=ROUND_HALF_UP),
        "esperado": esperado,
        "semaforo": semaforo(razon_global, esperado),
    })
    return resultado