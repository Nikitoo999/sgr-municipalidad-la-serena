from django.core.management.base import BaseCommand

from sgr_core.models import AttentionSubtype, AttentionType

# (código, nombre, descripción)
TIPOS = [
    ("TIP01", "Informes sociales", "Informes sociales de aporte económico, material o institucional."),
    ("TIP02", "Gestión de subsidios", "Postulación y gestión de subsidios y beneficios."),
    ("TIP03", "Derivaciones", "Derivación de casos a otros servicios."),
    ("TIP04", "Entrega de emergencia", "Entregas por emergencia."),
    ("TIP05", "Otras gestiones sociales", "Gestiones sociales no clasificadas en otro tipo."),
]

# (código, nombre, código del tipo)
SUBTIPOS = [
    ("SUB01", "Informe aporte económico", "TIP01"),
    ("SUB02", "Informe aporte material", "TIP01"),
    ("SUB03", "Informe institución", "TIP01"),
    ("SUB04", "IPS", "TIP02"),
    ("SUB05", "PGU", "TIP02"),
    ("SUB06", "SUF", "TIP02"),
    ("SUB07", "SAP", "TIP02"),
    ("SUB08", "Exención pago aseo domiciliario", "TIP02"),
    ("SUB09", "Orientación social", "TIP03"),
    ("SUB10", "Otros", "TIP03"),
    ("SUB11", "Emergencia", "TIP04"),
    ("SUB12", "Orientación social", "TIP05"),
    ("SUB13", "Otros", "TIP05"),
]


class Command(BaseCommand):
    help = "Carga el catálogo real de tipos y sub atenciones del Excel municipal (idempotente)."

    def handle(self, *args, **options):
        tipos = {}
        for code, name, description in TIPOS:
            tipo, _ = AttentionType.objects.update_or_create(
                code=code,
                defaults={"name": name, "description": description, "status": "Activo"},
            )
            tipos[code] = tipo
        for code, name, type_code in SUBTIPOS:
            AttentionSubtype.objects.update_or_create(
                code=code,
                defaults={"name": name, "attention_type": tipos[type_code], "status": "Activo"},
            )
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo listo: {len(TIPOS)} tipos y {len(SUBTIPOS)} sub atenciones."
        ))