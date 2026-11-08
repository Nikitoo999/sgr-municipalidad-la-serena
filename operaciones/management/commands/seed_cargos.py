from django.core.management.base import BaseCommand

from sgr_core.models import Position

CARGOS = [
    {
        "code": "CAR01",
        "name": "Delegado",
        "is_evaluated": False,
        "summary": (
            "Representante directo de la alcaldía en su territorio; puente entre "
            "el municipio y los sectores, apoya a dirigentes y gestiona soluciones locales."
        ),
        "functions": "\n".join([
            "Informar a la autoridad comunal sobre situaciones del territorio.",
            "Representar a la máxima autoridad comunal en su territorio.",
            "Velar por el buen funcionamiento interno y administrativo de la Delegación.",
            "Visitar periódicamente Juntas de Vecinos y organizaciones comunitarias.",
            "Proponer y dar soluciones a las necesidades de los usuarios del sector.",
            "Supervisar el cumplimiento de planes y políticas de desarrollo.",
            "Mantener comunicación con direcciones, departamentos y organizaciones.",
            "Difundir los programas y actividades de la Municipalidad.",
            "Delegar los trabajos de la comunidad a su equipo y guiar su desempeño.",
            "Generar mesas de trabajo con estamentos públicos y privados.",
            "Ejecutar otras funciones que le encomiende el alcalde o el Administrador Municipal.",
        ]),
    },
    {
        "code": "CAR02",
        "name": "Gestor Social",
        "is_evaluated": True,
        "summary": (
            "Desarrolla acciones comunitarias y atención de casos para promover el "
            "bienestar de los ciudadanos, en especial de quienes están en situación de vulnerabilidad."
        ),
        "functions": "\n".join([
            "Atención de casos: recepción, evaluación, diagnóstico, intervención y seguimiento.",
            "Derivación y articulación con otros servicios; visitas en terreno.",
            "Acciones comunitarias: diagnóstico, planificación y ejecución de programas.",
            "Organización y participación comunitaria; articulación con organizaciones de apoyo social.",
            "Coordinación con otros servicios y programas municipales.",
            "Gestión de recursos para la atención de casos y programas comunitarios.",
            "Elaboración de informes y estadísticas de atención y acciones comunitarias.",
            "Participación en reuniones y comités, capacitación y apoyo a la gestión municipal.",
        ]),
    },
        {
        "code": "CAR03",
        "name": "Apoyo Administrativo",
        "is_evaluated": True,
        "summary": (
            "Brinda asistencia en gestión documental y atención ciudadana; gestiona la "
            "agenda y logística de la delegación, los expedientes y la base de datos."
        ),
        "functions": "\n".join([
            "Llevar la agenda del delegado y coordinar eventos y reuniones.",
            "Coordinar el transporte de la delegación.",
            "Encargarse de los auxiliares, la mantención y el aseo.",
            "Atender público y derivar a las áreas correspondientes.",
            "Generar el registro de atenciones (planilla SGR) para llamadas preventivas a usuarios.",
            "Generar el inventario trimestral de la delegación.",
            "Entregar materiales a los funcionarios.",
            "Retroalimentar al delegado con las solicitudes ingresadas por la comunidad.",
            "Elaborar informes mensuales del personal administrativo.",
            "Enviar la agenda a Comunicaciones.",
            "Otros procesos administrativos para cumplir los objetivos de la Delegación.",
        ]),
    },
    {
        "code": "CAR04",
        "name": "Organizaciones Comunitarias",
        "is_evaluated": True,
        "summary": (
            "Responsable del Registro de Organizaciones (OROC) y de facilitar la formación, "
            "legalización y asesoría de juntas de vecinos y agrupaciones funcionales "
            "(leyes 19.418 y 20.500)."
        ),
        "functions": "\n".join([
            "Potenciar el desarrollo de los territorios en beneficio de la comunidad.",
            "Crear organizaciones nuevas y mantener la vigencia o cierre de las inactivas.",
            "Asesorar y capacitar a las organizaciones en temas y procedimientos.",
            "Levantar necesidades en cada territorio junto a los dirigentes.",
            "Generar las convocatorias a las actividades municipales.",
            "Articular a las organizaciones con las áreas municipales.",
            "Generar actividades y talleres para las organizaciones.",
            "Otros procesos administrativos para cumplir los objetivos de la Delegación.",
        ]),
    },
    {
        "code": "CAR05",
        "name": "Gestor de Compras y Proyectos",
        "is_evaluated": False,  # el Excel no trae ítems para este cargo; confirmar con el grupo
        "summary": (
            "Tramita los requerimientos de adquisición de bienes y servicios ante las "
            "unidades que intervienen en el proceso de compra."
        ),
        "functions": "\n".join([
            "Recopilar y confeccionar la planificación operativa anual de la dirección.",
            "Controlar el cumplimiento del Plan Anual de Compras.",
            "Revisar pliegos, marcos de referencia y especificaciones técnicas.",
            "Elaborar solicitudes u oficios internos de contratación con la debida anticipación.",
            "Proponer la Comisión Evaluadora y el Inspector Técnico de Contrato.",
        ]),
    },
    {
        "code": "CAR06",
        "name": "Gestión y Planificación",
        "is_evaluated": True,
        "summary": (
            "Alinea los objetivos estratégicos con las operaciones diarias de la delegación, "
            "monitorea indicadores y apoya la toma de decisiones."
        ),
        "functions": "\n".join([
            "Derivar y apoyar a cada área en los informes solicitados por la jefatura.",
            "Apoyar el diagnóstico de necesidades de la comunidad del sector.",
            "Mantener el buen funcionamiento de los procesos internos y derivar tareas diarias.",
            "Informar al delegado sobre el trabajo de la matriz SGR y las fortalezas y debilidades del equipo.",
            "Informar oportunamente al delegado sobre materias de interés del sector.",
            "Coordinar con departamentos internos y con la coordinación de delegaciones.",
            "Tomar acciones rápidas ante problemas derivados desde Gabinete.",
            "Representar a la delegación cuando el delegado lo solicite.",
            "Velar por el correcto llenado de la matriz SGR.",
            "Gestionar la reunión semanal.",
        ]),
    },
    {
        "code": "CAR07",
        "name": "Coordinador de Servicios Comunitarios",
        "is_evaluated": True,
        "summary": (
            "Planifica, coordina y ejecuta iniciativas de aseo, ornato y medio ambiente "
            "en beneficio de la comunidad."
        ),
        "functions": "\n".join([
            "Ser enlace entre la Municipalidad y juntas de vecinos, clubes y agrupaciones ambientales.",
            "Atender usuarios presencialmente y en terreno cuando se requiere análisis técnico.",
            "Coordinar operativos de limpieza, desmalezado y recuperación de espacios.",
            "Liderar acciones de educación ambiental (reciclaje, compostaje, aseo y ornato).",
            "Velar por las cuadrillas del programa de empleabilidad y de emergencia.",
            "Coordinar con direcciones municipales (Aseo y Ornato, Operaciones, maquinarias).",
            "Recibir y dar seguimiento a denuncias ciudadanas sobre uso indebido de espacios públicos.",
            "Elaborar informes de gestión periódicos del programa de empleabilidad.",
            "Otros procesos administrativos del área de servicios a la comunidad.",
        ]),
    },
]


class Command(BaseCommand):
    help = "Carga o actualiza los cargos de las delegaciones (idempotente)."

    def handle(self, *args, **options):
        for datos in CARGOS:
            code = datos["code"]
            _, creado = Position.objects.update_or_create(
                code=code,
                defaults={k: v for k, v in datos.items() if k != "code"},
            )
            estado = "creado" if creado else "actualizado"
            self.stdout.write(f"{code} {datos['name']}: {estado}")
        self.stdout.write(self.style.SUCCESS("Cargos listos."))