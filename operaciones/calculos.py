from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import chain

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from operaciones.models import Activity, Attention, EmployeeFeedback, TubeEntry
from operaciones.periodos import tubos_originados_en
from sgr_core.models import Period, PositionItemGoal

CENTESIMOS = Decimal("0.01")


def periodo_vigente(hoy=None):
    """Trimestre de medición vigente.

    Es el período (no borrado) cuyo rango contiene ``hoy``; si hay varios, el
    "En curso" más reciente. Si ninguno contiene la fecha, el "En curso" más
    reciente y, en último caso, el más reciente. Todas las pantallas usan esta
    regla para no mostrar trimestres distintos según el módulo.
    """
    hoy = hoy or date.today()
    vivos = Period.objects.filter(deleted_at__isnull=True)
    en_fecha = vivos.filter(start_date__lte=hoy, end_date__gte=hoy)
    return (
        en_fecha.filter(status="En curso").order_by("-start_date", "-pk").first()
        or en_fecha.order_by("-start_date", "-pk").first()
        or vivos.filter(status="En curso").order_by("-start_date", "-pk").first()
        or vivos.order_by("-start_date", "-pk").first()
    )


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
    if "days_off" in getattr(employee, "_prefetched_objects_cache", {}):
        # Listados de equipo: los días libres vienen precargados (una consulta
        # para todos los funcionarios en vez de varias por funcionario).
        registros = [
            r for r in employee.days_off.all()
            if r.deleted_at is None and r.start_date <= period.end_date and r.end_date >= period.start_date
        ]
    else:
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


def _actividades_que_suman(employee, period, delegation_id):
    """(fecha, item_id, orden) de actividades realizadas con evidencia aprobada.

    Punto 2 del nuevo requerimiento: si el ítem es de cara al usuario
    (``requires_contact``), la actividad debe traer nombre y teléfono.
    """
    actividades = Activity.objects.all()
    if delegation_id is not None:
        actividades = actividades.filter(task__goal__delegation_id=delegation_id)
    filas = (
        actividades.filter(
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
        .values_list("pk", "execution_date", "item_id", "item__requires_contact",
                     "contact_name", "contact_phone")
        .distinct()
    )
    for pk, dia, item_id, exige_contacto, nombre, telefono in filas:
        if exige_contacto and not ((nombre or "").strip() and (telefono or "").strip()):
            continue
        yield dia, item_id, (0, pk)


def _atenciones_que_suman(employee, period, delegation_id):
    """(fecha, item_id, orden) de atenciones que aportan a la matriz.

    Deben: tener ítem, contar para el puntaje (no preparatoria, no gestión
    interna, no ingreso propio ni del Delegado), validación aprobada (RN-009)
    y nombre y teléfono del solicitante (punto 2).
    """
    inicio = timezone.make_aware(datetime.combine(period.start_date, time.min))
    fin = timezone.make_aware(datetime.combine(period.end_date + timedelta(days=1), time.min))
    atenciones = Attention.objects.all()
    if delegation_id is not None:
        atenciones = atenciones.filter(delegation_id=delegation_id)
    filas = (
        atenciones.filter(
            deleted_at__isnull=True,
            responsible_id=employee.user_id,
            item__isnull=False,
            counts_for_score=True,
            validation_status="approved",
            created_at__gte=inicio, created_at__lt=fin,
        )
        .exclude(neighbor__phone="").exclude(neighbor__full_name="")
        .order_by("created_at", "pk")
        .values_list("pk", "created_at", "item_id")
    )
    for pk, momento, item_id in filas:
        yield timezone.localtime(momento).date(), item_id, (1, pk)


def logrado_por_item(employee, period, *, delegation_id=None):
    """Registros que suman por ítem dentro del trimestre.

    Suman las actividades de la agenda realizadas con evidencia aprobada y las
    atenciones aprobadas (ver ``_actividades_que_suman`` y
    ``_atenciones_que_suman``). Cada día cuenta a lo más
    MAX_ACTIVIDADES_POR_DIA registros entre ambos (punto 3).
    """
    logrado = defaultdict(int)
    for _dia, item_id in registros_contados(employee, period, delegation_id=delegation_id):
        logrado[item_id] += 1
    return dict(logrado)


def registros_contados(employee, period, *, delegation_id=None):
    """(fecha, item_id) de cada registro que suma, ya aplicado el tope diario."""
    registros = sorted(
        chain(
            _actividades_que_suman(employee, period, delegation_id),
            _atenciones_que_suman(employee, period, delegation_id),
        ),
        key=lambda fila: (fila[0], fila[2]),
    )
    por_dia = defaultdict(int)
    contados = []
    for dia, item_id, _orden in registros:
        if por_dia[dia] < MAX_ACTIVIDADES_POR_DIA:
            por_dia[dia] += 1
            contados.append((dia, item_id))
    return contados


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


def razon_tubo(employee, period, *, tubos=None):
    """Fracción de solicitudes del tubo realizadas (None si no tuvo solicitudes en el trimestre).

    Nuevo requerimiento (punto 2): una solicitud realizada sin nombre y teléfono
    del solicitante no tiene puntuación (sigue contando como solicitud).
    """
    if tubos is None:
        tubos = TubeEntry.alive.filter(source_task__deleted_at__isnull=True).filter(
            # Del trimestre o traspasadas a él con prioridad al cerrar el anterior.
            tubos_originados_en(period) | Q(carried_to_period=period)
        )
    filas = list(
        tubos.filter(responsible=employee).exclude(status=TubeEntry.Status.NOT_APPLICABLE)
        .values_list("status", "requester", "contact_phone")
    )
    if not filas:
        return None
    realizadas = sum(
        1 for estado, solicitante, telefono in filas
        if estado == TubeEntry.Status.DONE
        and (solicitante or "").strip() and (telefono or "").strip()
    )
    return Decimal(realizadas) / Decimal(len(filas))


#: Código del ítem "Soluciones de ingresos al tubo": se mide en % de solicitudes realizadas.
CODIGO_ITEM_TUBO = "MTX06"


def calcular_cumplimiento(employee, period, hoy=None, *, delegation_id=None, tubos=None):
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
    logrado = logrado_por_item(employee, period, delegation_id=delegation_id)
    factor = factor_ajuste(employee, period)
    esperado = avance_esperado(employee, period, hoy)

    total, suma_pesos = Decimal("0"), Decimal("0")
    fraccion_tubo = None
    tubo_calculado = False
    for goal in metas:
        es_tubo = goal.item.code == CODIGO_ITEM_TUBO
        if es_tubo:
            if not tubo_calculado:
                fraccion_tubo = razon_tubo(employee, period, tubos=tubos)
                tubo_calculado = True
            meta = goal.target_value                              # es un %, no se ajusta por días libres
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


# --- Ingresos diarios y días sin ingresar (3.7) ------------------------------

def _rango_de_fechas(period, hasta=None):
    """Inicio y fin (con zona horaria) del trimestre, o hasta una fecha."""
    ultimo = min(hasta, period.end_date) if hasta else period.end_date
    inicio = timezone.make_aware(datetime.combine(period.start_date, time.min))
    fin = timezone.make_aware(datetime.combine(ultimo, time.max))
    return inicio, fin


def ingresos_por_dia(employee, period, hasta=None, *, delegation_id=None):
    """Cuántas atenciones y actividades ingresó el funcionario cada día (por fecha de ingreso)."""
    inicio, fin = _rango_de_fechas(period, hasta)
    atenciones = Attention.objects.filter(
        responsible_id=employee.user_id, deleted_at__isnull=True,
        created_at__range=(inicio, fin),
    )
    actividades = Activity.objects.filter(
        task__assigned_to=employee, deleted_at__isnull=True,
        created_at__range=(inicio, fin),
    )
    if delegation_id is not None:
        atenciones = atenciones.filter(delegation_id=delegation_id)
        actividades = actividades.filter(task__goal__delegation_id=delegation_id)
    return Counter(
        timezone.localtime(momento).date()
        for momento in chain(
            atenciones.values_list("created_at", flat=True),
            actividades.values_list("created_at", flat=True),
        )
    )


def dias_sin_ingresar(employee, period, hoy, *, delegation_id=None):
    """Días hábiles sin ningún ingreso, hasta ayer y sin contar los días libres."""
    hasta = min(hoy - timedelta(days=1), period.end_date)
    if hasta < period.start_date:
        return []
    exigidos = set(dias_habiles(period.start_date, hasta)) - dias_libres(employee, period)
    con_ingreso = set(ingresos_por_dia(employee, period, hasta, delegation_id=delegation_id))
    return sorted(exigidos - con_ingreso)


def dias_sobre_el_limite(employee, period, *, delegation_id=None):
    """Días en que el funcionario ingresó más de MAX_ACTIVIDADES_POR_DIA."""
    return sorted(
        dia for dia, cantidad in ingresos_por_dia(employee, period, delegation_id=delegation_id).items()
        if cantidad > MAX_ACTIVIDADES_POR_DIA
    )

# --- Resumen de delegación (RF-029/RF-030, diapositivas 18 y 19) -----------------


def actividad_reciente(employee, period, hoy, *, delegation_id=None):
    """Último ingreso, días desde él, cantidad de ingresos y promedio diario.

    Ingresos = atenciones y actividades registradas por el funcionario en el
    trimestre (hasta hoy). El promedio se calcula sobre los días hábiles
    efectivos transcurridos (sin días libres).
    """
    ingresos = ingresos_por_dia(employee, period, hoy, delegation_id=delegation_id)
    total = sum(ingresos.values())
    ultimo = max(ingresos) if ingresos else None
    dias = dias_efectivos(employee, period, hoy)
    return {
        "ultimo": ultimo,
        "dias_desde_ultimo": (hoy - ultimo).days if ultimo else None,
        "total": total,
        "promedio": (Decimal(total) / Decimal(dias)).quantize(CENTESIMOS) if dias else Decimal("0.00"),
    }


def resumen_equipo(filas):
    """Puntaje del equipo e ítems a reforzar (correo, puntos 7 y 10).

    ``filas`` son dicts con ``empleado`` y ``cumplimiento`` (de
    ``calcular_cumplimiento``). Solo cuentan los cargos que se evalúan en la
    matriz (no el Delegado). El semáforo del equipo compara el promedio con el
    avance esperado promedio, con la misma regla que el individual.
    """
    evaluados = [
        f for f in filas
        if f["empleado"].position_id and f["empleado"].position.is_evaluated
        and f["cumplimiento"]["items"]
    ]
    if not evaluados:
        return None
    n = Decimal(len(evaluados))
    promedio = sum(f["cumplimiento"]["porcentaje"] for f in evaluados) / n
    esperado = sum(f["cumplimiento"]["esperado"] for f in evaluados) / n
    conteo = Counter(f["cumplimiento"]["semaforo"] for f in evaluados)
    por_item = defaultdict(list)
    for f in evaluados:
        for it in f["cumplimiento"]["items"]:
            por_item[it["item"]].append(min(it["razon"], TOPE_CUMPLIMIENTO))
    items = sorted(
        (
            {"item": item, "logro_pct": (sum(v) / Decimal(len(v)) * 100).quantize(Decimal("0.1")),
             "funcionarios": len(v)}
            for item, v in por_item.items()
        ),
        key=lambda x: x["logro_pct"],
    )
    return {
        "evaluados": len(evaluados),
        "porcentaje": promedio.quantize(CENTESIMOS),
        "esperado_pct": (esperado * 100).quantize(Decimal("0.1")),
        "semaforo": semaforo(promedio / 100, esperado),
        "verdes": conteo.get("verde", 0),
        "amarillos": conteo.get("amarillo", 0),
        "rojos": conteo.get("rojo", 0),
        "items_a_reforzar": items[:5],
    }
