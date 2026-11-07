import re
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sgr_core.models import CommunityOrganization, Delegation

# Territorio de la base -> código de delegación.
# ALFALFARES no se asigna: el grupo debe confirmar a qué delegación corresponde.
TERRITORIO_A_DELEGACION = {
    "CENTRO": "DEL01",
    "AV DEL MAR": "DEL02",
    "ANTENA": "DEL03",
    "CIAS": "DEL04",
    "PAMPA": "DEL05",
    "RURAL": "DEL06",
}

# Reglas de categoría, en orden de prioridad: la primera que coincide gana.
# (categoría, "empieza con", "contiene")
REGLAS_CATEGORIA = [
    ("committee", ("COMITE",), ()),
    ("neighborhood", ("JJVV", "J.V"), ("JUNTA DE VECINOS", "JUNTA VECINAL", "ORGANIZACION VECINAL",
                                    "AGRUPACION VECINAL", "CONSEJO VECINAL", "UNIDAD VECINAL")),
    ("senior", ("CAM ",), ("ADULTO", "MAYORES", "TERCERA EDAD")),
    ("sports", (), ("DEPORT", "FUTBOL", "BASQUET", "VOLEI", "ATLET", "TAEKWON", "AJEDREZ", "CICLI", "NATACION")),
    ("cultural", ("CENTRO DE MADRES", "CENTRO CULTURAL"),
    ("CULTURAL", "JUVENIL", "JOVENES", "FOLCLOR", "BAILE", "BALLET", "CORO ", "ORQUESTA",
    "ARTISTIC", "TEATRO", "MUSICA", "DANZA", "TALLER", "CENTRO DE MADRES")),
]


def sin_acentos(texto):
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def limpiar_texto(valor):
    """Quita espacios sobrantes (inicio, fin y repetidos). None/vacío -> ''."""
    if valor is None:
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip()


def es_sin_info(texto):
    """True si el texto es una forma de 'sin información' (S/Inf., SIN INF., etc.)."""
    clave = re.sub(r"[.\s]", "", sin_acentos(texto).upper())
    return clave in {"S/INF", "SININF", "S/I", "SININFORMACION", "N/A", "SD"}


def clasificar(nombre):
    base = sin_acentos(nombre).upper()
    for categoria, empieza, contiene in REGLAS_CATEGORIA:
        if base.startswith(empieza) if empieza else False:
            return categoria
        if any(frag in base for frag in contiene):
            return categoria
    return "other"


def a_fecha(valor):
    """Devuelve (fecha o None, texto_original_si_no_era_fecha_valida)."""
    if isinstance(valor, datetime):
        return valor.date(), ""
    if isinstance(valor, date):
        return valor, ""
    texto = limpiar_texto(valor)
    if not texto or es_sin_info(texto):
        return None, ""
    for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date(), ""
        except ValueError:
            continue
    return None, texto


def a_entero(valor):
    """Devuelve (entero o None, texto_original_si_no_era_numerico)."""
    if valor is None:
        return None, ""
    if isinstance(valor, (int, float)):
        return int(valor), ""
    texto = limpiar_texto(valor)
    if not texto or es_sin_info(texto):
        return None, ""
    if texto.isdigit():
        return int(texto), ""
    return None, texto


def limpiar_fila(fila):
    """Convierte una fila cruda del Excel en un dict limpio + lista de observaciones."""
    notas = []
    nombre = limpiar_texto(fila[0])
    domicilio = limpiar_texto(fila[1])
    territorio = limpiar_texto(fila[2]).upper()

    codigo_deleg = TERRITORIO_A_DELEGACION.get(territorio)
    if not territorio:
        notas.append("sin territorio")
    elif codigo_deleg is None:
        notas.append(f"territorio sin delegación asignada: {territorio}")

    socios, socios_raw = a_entero(fila[3])
    if socios_raw:
        notas.append(f"socios no numérico: '{socios_raw}'")

    f_constit, constit_raw = a_fecha(fila[4])
    if constit_raw:
        notas.append(f"fecha de constitución inválida: '{constit_raw}'")
    f_inscr, inscr_raw = a_fecha(fila[6])
    if inscr_raw:
        notas.append(f"fecha de inscripción inválida: '{inscr_raw}'")
    if f_constit and f_inscr and f_inscr < f_constit:
        notas.append("inscripción anterior a la constitución")

    return {
        "name": nombre,
        "legal_address": domicilio,
        "territory": territorio,
        "delegation_code": codigo_deleg,
        "category": clasificar(nombre),
        "active_members": socios,
        "constitution_date": f_constit,
        "registry_number": limpiar_texto(fila[5]),
        "registry_date": f_inscr,
        "directive_number": limpiar_texto(fila[7]),
        "notes": "; ".join(notas),
        "_notas": notas,
        "_nombre_original": fila[0],
    }


class Command(BaseCommand):
    help = "Limpia y carga la base de organizaciones comunitarias (JJVV y funcionales) desde un Excel."

    def add_arguments(self, parser):
        parser.add_argument(
            "archivo", nargs="?", default="data/base_datos_JJVV_sin_verificar.xlsx",
            help="Ruta del Excel (por defecto data/base_datos_JJVV_sin_verificar.xlsx).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Solo muestra el reporte de limpieza, sin escribir en la base.",
        )

    def handle(self, *args, **options):
        ruta = Path(options["archivo"])
        if not ruta.exists():
            raise CommandError(f"No encuentro el archivo: {ruta}")

        import openpyxl
        hoja = openpyxl.load_workbook(ruta, data_only=True).active
        filas = [f for f in hoja.iter_rows(min_row=2, values_only=True) if f and f[0]]

        limpias = [limpiar_fila(f) for f in filas]
        self._reporte(limpias)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Modo --dry-run: no se escribió nada."))
            return

        delegaciones = {d.code: d for d in Delegation.objects.filter(code__in=TERRITORIO_A_DELEGACION.values())}
        faltan = set(TERRITORIO_A_DELEGACION.values()) - set(delegaciones)
        if faltan:
            raise CommandError(
                f"Faltan delegaciones {sorted(faltan)}. Corre primero: python manage.py seed_demo"
            )

        creadas = actualizadas = 0
        with transaction.atomic():
            for d in limpias:
                _, creada = CommunityOrganization.objects.update_or_create(
                    registry_number=d["registry_number"],
                    name=d["name"],
                    defaults={
                        "legal_address": d["legal_address"],
                        "territory": d["territory"],
                        "delegation": delegaciones.get(d["delegation_code"]),
                        "category": d["category"],
                        "active_members": d["active_members"],
                        "constitution_date": d["constitution_date"],
                        "registry_date": d["registry_date"],
                        "directive_number": d["directive_number"],
                        "notes": d["notes"],
                    },
                )
                if creada:
                    creadas += 1
                else:
                    actualizadas += 1
        self.stdout.write(self.style.SUCCESS(
            f"Organizaciones: {creadas} creadas, {actualizadas} actualizadas."
        ))

    def _reporte(self, limpias):
        w = self.stdout.write
        w(f"\nFilas leídas: {len(limpias)}")
        w(f"Nombres con espacios corregidos: {sum(1 for d in limpias if str(d['_nombre_original']) != d['name'])}")
        w(f"Sin domicilio legal: {sum(1 for d in limpias if not d['legal_address'])}")
        w(f"Sin fecha de constitución: {sum(1 for d in limpias if d['constitution_date'] is None)}")
        w(f"Sin dato de socios: {sum(1 for d in limpias if d['active_members'] is None)}")

        w("\nPor categoría:")
        for cat, n in Counter(d["category"] for d in limpias).most_common():
            w(f"  {cat}: {n}")

        w("\nPor delegación (código; None = sin asignar):")
        for cod, n in sorted(Counter(d["delegation_code"] for d in limpias).items(), key=lambda x: str(x[0])):
            w(f"  {cod}: {n}")

        w("\nObservaciones dejadas en la ficha:")
        tipos = Counter()
        for d in limpias:
            for nota in d["_notas"]:
                tipos[nota.split(":")[0]] += 1
        for nota, n in tipos.most_common():
            w(f"  {nota}: {n}")

        claves = Counter((d["registry_number"], d["name"]) for d in limpias)
        repetidas = [k for k, v in claves.items() if v > 1]
        w(f"\nClaves (N° registro + nombre) repetidas en el archivo: {len(repetidas)}")
        por_registro = Counter(d["registry_number"] for d in limpias)
        w(f"N° de registro repetidos (nombres distintos): {sum(1 for v in por_registro.values() if v > 1)}")