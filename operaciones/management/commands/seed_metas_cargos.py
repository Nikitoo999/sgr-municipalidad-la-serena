from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from sgr_core.models import Period, Position, PositionItemGoal, ProjectItem

# Ítems de la matriz (catálogo ProjectItem, códigos MTX para no chocar con los ITM del seed_demo)
ITEMS = {
    "MTX01": "Atención social a usuario presencial",
    "MTX02": "Visita en terreno",
    "MTX03": "Entrega de informe",
    "MTX04": "Entrega de beneficio",
    "MTX05": "Emergencia",
    "MTX06": "Soluciones de ingresos al tubo",
    "MTX07": "Atención de usuario teléfono y presencial",
    "MTX08": "Llamadas preventivas a usuarios",
    "MTX09": "Informe de inventarios",
    "MTX10": "Informe a comunicaciones",
    "MTX11": "Visitas y reuniones con organizaciones",
    "MTX12": "Conformación de organizaciones",
    "MTX13": "Gestión de talleres y actividades",
    "MTX14": "Informes de personal",
    "MTX15": "Informe de trabajo",
    "MTX16": "Operativo de la delegación",
    "MTX17": "Operativo Diserco",
    "MTX18": "Talleres",
    "MTX19": "Terreno",
    "MTX20": "Atención de requerimiento de usuario",
    "MTX21": "Reunión semanal con el equipo",
    "MTX22": "Solución de problemas a usuarios particulares",
}

# código de cargo -> lista de (código de ítem, ponderador en %, meta del trimestre)
# Valores tomados del Excel municipal como base; se ajustan editando esta tabla.
METAS = {
    "CAR02": [  # Gestor Social
        ("MTX01", 25, 90),
        ("MTX02", 20, 12),
        ("MTX03", 20, 40),
        ("MTX04", 20, 8),
        ("MTX05", 5, 0),     # la meta de emergencia varía por persona: se ajusta aparte
        ("MTX06", 10, 0.8),
    ],
    "CAR03": [  # Apoyo Administrativo
        ("MTX07", 20, 240),
        ("MTX08", 30, 90),
        ("MTX09", 25, 1),
        ("MTX10", 20, 12),
        ("MTX05", 5, 0),
    ],
        "CAR04": [  # Organizaciones Comunitarias
        ("MTX07", 15, 60),
        ("MTX11", 15, 24),
        ("MTX12", 25, 1),
        ("MTX13", 15, 6),
        ("MTX05", 5, 0),
        ("MTX06", 25, 0.8),
    ],
    "CAR06": [  # Gestión y Planificación (el Excel suma solo 85%)
        ("MTX21", 15, 12),
        ("MTX22", 30, 8),
        ("MTX05", 5, 0),
        ("MTX06", 35, 0.8),
    ],
    "CAR07": [  # Coordinador de Servicios Comunitarios
        ("MTX14", 10, 3),
        ("MTX15", 10, 12),
        ("MTX16", 15, 24),
        ("MTX17", 10, 12),
        ("MTX18", 10, 12),
        ("MTX19", 10, 24),
        ("MTX20", 15, 24),
        ("MTX05", 5, 0),
        ("MTX06", 15, 0.8),
    ],
}


class Command(BaseCommand):
    help = "Carga ítems, ponderadores y metas por cargo para el trimestre actual (idempotente)."

    def handle(self, *args, **options):
        periodo, _ = Period.objects.get_or_create(
            name="Trimestre Oct-Dic 2026",
            defaults={
                "start_date": date(2026, 10, 1),
                "end_date": date(2026, 12, 31),
                "quarter": 4,
                "status": "En curso",
            },
        )

        for code, name in ITEMS.items():
            ProjectItem.objects.update_or_create(
                code=code, defaults={"name": name, "status": "Activo"},
            )

        for pos_code, filas in METAS.items():
            try:
                cargo = Position.objects.get(code=pos_code)
            except Position.DoesNotExist:
                raise CommandError(
                    f"Falta el cargo {pos_code}. Corre primero: python manage.py seed_cargos"
                )

            total = sum(Decimal(str(peso)) for _, peso, _ in filas)
            if total != 100:
                self.stdout.write(self.style.WARNING(
                    f"{cargo.name}: los ponderadores suman {total}%, no 100%."
                ))

            for item_code, peso, meta in filas:
                PositionItemGoal.objects.update_or_create(
                    position=cargo,
                    item=ProjectItem.objects.get(code=item_code),
                    period=periodo,
                    defaults={
                        "weight": Decimal(str(peso)),
                        "target_value": Decimal(str(meta)),
                    },
                )
            self.stdout.write(f"{cargo.name}: {len(filas)} ítems (suma {total}%)")

        self.stdout.write(self.style.SUCCESS(f"Metas cargadas para {periodo.name}."))