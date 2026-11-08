"""Cálculos compartidos de la matriz SGR (días hábiles y metas ajustadas)."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

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