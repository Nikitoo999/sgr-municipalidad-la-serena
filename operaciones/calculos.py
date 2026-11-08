from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import chain

from django.conf import settings
from django.utils import timezone

from operaciones.models import Activity, Attention, EmployeeFeedback, TubeEntry
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
#: Felicitaciones y reclamos (configurables en settings.py).
PUNTOS_FELICITACION = Decimal(str(getattr(settings, "SGR_PUNTOS_FELICITACION", "10")))
MAX_FELICITACIONES = int(getattr(settings, "SGR_MAX_FELICITACIONES", 3))
PUNTOS_RECLAMO = Decimal(str(getattr(settings, "SGR_PUNTOS_RECLAMO", "20")))


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


def conteo_comentarios(employee, period):
    """(felicitaciones con respaldo, reclamos) del funcionario dentro del trimestre."""
    registros = EmployeeFeedback.objects.filter(
        employee=employee, deleted_at__isnull=True,
        date__range=(period.start_date, period.end_date),
    ).values_list("kind", "file")
    felicitaciones = sum(1 for kind, archivo in registros
                        if kind == EmployeeFeedback.Kind.PRAISE and archivo)
    reclamos = sum(1 for kind, _archivo in registros
                if kind == EmployeeFeedback.Kind.COMPLAINT)
    return felicitaciones, reclamos


def puntos_felicitaciones(cantidad):
    """Puntos que suman las felicitaciones (tope de MAX_FELICITACIONES)."""
    return Decimal(min(cantidad, MAX_FELICITACIONES)) * PUNTOS_FELICITACION


def puntos_reclamos(cantidad):
    """Puntos que restan los reclamos."""
    return Decimal(cantidad) * PUNTOS_RECLAMO


def razon_tubo(employee, period):
    """Fracción de solicitudes del tubo realizadas (None si no tuvo solicitudes en el trimestre)."""
    estados = list(
        TubeEntry.objects.filter(
            responsible=employee, deleted_at__isnull=True,
            request_date__range=(period.start_date, period.end_date),
        ).exclude(status=TubeEntry.Status.NOT_APPLICABLE).values_list("status", flat=True)
    )
    if not estados:
        return None
    realizadas = sum(1 for estado in estados if estado == TubeEntry.Status.DONE)
    return Decimal(realizadas) / Decimal(len(estados))



def calcular_cumplimiento(employee, period, hoy=None):
    """Cumplimiento de un funcionario en un trimestre, ítem por ítem."""
    hoy = hoy or date.today()
    resultado = {
        "items": [], "puntaje_total": Decimal("0.00"), "suma_pesos": Decimal("0"),
        "porcentaje": Decimal("0.00"), "esperado": Decimal("0"), "semaforo": "verde",
        "felicitaciones": 0, "reclamos": 0,
        "bonus": Decimal("0"),  "descuento": Decimal("0"),
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
            fraccion_tubo = None
    tubo_calculado = False
    for goal in metas:
        es_tubo = goal.item.code == CODIGO_ITEM_TUBO
        if es_tubo:
            if not tubo_calculado:
                fraccion_tubo = razon_tubo(employee, period)
                tubo_calculado = True
            meta = goal.target_value                       # es un %, no se ajusta por días libres
            hecho = fraccion_tubo
            razon = Decimal("1") if hecho is None else razon_logro(hecho, meta)
        else:
            meta = meta_ajustada(goal.target_value, factor)
            hecho = logrado.get(goal.item_id, 0)
            razon = razon_logro(hecho, meta)
        puntaje = puntaje_item(razon, goal.weight)
        total += puntaje
        suma_pesos += goal.weight
        resultado["items"].append({
            "item": goal.item, "peso": goal.weight, "meta": meta, "logrado": hecho,
            "razon": razon, "puntaje": puntaje, "semaforo": semaforo(razon, esperado),
                    "es_tubo": es_tubo,
            "logrado_txt": (
                ("Sin solicitudes" if hecho is None else f"{(hecho * 100).quantize(Decimal('0.1'))} % realizado")
                if es_tubo else None
            ),
            "meta_txt": f"{(meta * 100).quantize(Decimal('1'))} %" if es_tubo else None,
        })

        felicitaciones, reclamos = conteo_comentarios(employee, period)
    bonus = puntos_felicitaciones(felicitaciones)
    descuento = puntos_reclamos(reclamos)
    total = max(total + bonus - descuento, Decimal("0"))

    razon_global = (total / suma_pesos) if suma_pesos else Decimal("0")
    resultado.update({
        "puntaje_total": total.quantize(CENTESIMOS),
        "suma_pesos": suma_pesos,
        "porcentaje": (razon_global * 100).quantize(CENTESIMOS, rounding=ROUND_HALF_UP),
        "esperado": esperado,
        "semaforo": semaforo(razon_global, esperado),
        "felicitaciones": felicitaciones,
        "reclamos": reclamos,
        "bonus": bonus,
        "descuento": descuento,
    })
    return resultado
#: Código del ítem "Soluciones de ingresos al tubo": se mide en % de solicitudes realizadas.
CODIGO_ITEM_TUBO = "MTX06"

# --- Ingresos diarios y días sin ingresar (3.7) ------------------------------

def _rango_de_fechas(period, hasta=None):
    """Inicio y fin (con zona horaria) del trimestre, o hasta una fecha."""
    ultimo = min(hasta, period.end_date) if hasta else period.end_date
    inicio = timezone.make_aware(datetime.combine(period.start_date, time.min))
    fin = timezone.make_aware(datetime.combine(ultimo, time.max))
    return inicio, fin


def ingresos_por_dia(employee, period, hasta=None):
    """Cuántas atenciones y actividades ingresó el funcionario cada día (por fecha de ingreso)."""
    inicio, fin = _rango_de_fechas(period, hasta)
    atenciones = Attention.objects.filter(
        responsible_id=employee.user_id, deleted_at__isnull=True,
        created_at__range=(inicio, fin),
    ).values_list("created_at", flat=True)
    actividades = Activity.objects.filter(
        task__assigned_to=employee, deleted_at__isnull=True,
        created_at__range=(inicio, fin),
    ).values_list("created_at", flat=True)
    return Counter(
        timezone.localtime(momento).date() for momento in chain(atenciones, actividades)
    )


def dias_sin_ingresar(employee, period, hoy):
    """Días hábiles sin ningún ingreso, hasta ayer y sin contar los días libres."""
    hasta = min(hoy - timedelta(days=1), period.end_date)
    if hasta < period.start_date:
        return []
    exigidos = set(dias_habiles(period.start_date, hasta)) - dias_libres(employee, period)
    con_ingreso = set(ingresos_por_dia(employee, period, hasta))
    return sorted(exigidos - con_ingreso)


def dias_sobre_el_limite(employee, period):
    """Días en que el funcionario ingresó más de MAX_ACTIVIDADES_POR_DIA."""
    return sorted(
        dia for dia, cantidad in ingresos_por_dia(employee, period).items()
        if cantidad > MAX_ACTIVIDADES_POR_DIA
    )