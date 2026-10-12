"""
Carga datos ficticios de demostración para el SGR (modelos actualizados).

Uso:
    python manage.py seed_demo

Es idempotente: se puede ejecutar varias veces sin duplicar registros.
Todos los funcionarios, RUT, correos y URLs de evidencia son FICTICIOS
(la guía del proyecto prohíbe cargar datos reales de funcionarios o
ciudadanos). Las delegaciones y sus descripciones corresponden a
información pública de la Municipalidad de La Serena.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalogos.models import AttentionSubtype, AttentionType
from operaciones.models import Activity, Benefit, Employee, Evidence, Task, TaskReassignment
from sgr_core.models import Achievement, Delegation, InstitutionalGoal, MeasurementItem, Period

DEMO_PASSWORD = "Demo2026!"
ADMIN_USER = "admin_demo"
LIMITED_USER = "limitado_demo"
BOSS_USER = "jefatura_centro"

DELEGATIONS = [
    ("Avenida del Mar", "Borde costero, turismo, residencial y servicios", "#1D6FA5"),
    ("Centro", "Centro histórico, administrativo, comercial y patrimonial", "#C62828"),
    ("La Antena", "Sector urbano oriental y barrios asociados", "#2E7D32"),
    ("Las Compañías", "Sector urbano norte de alta densidad y fuerte identidad territorial", "#6A1B9A"),
    ("La Pampa", "Sector urbano sur y áreas residenciales asociadas", "#E65100"),
    ("Rural", "Localidades y comunidades rurales dispersas", "#00796B"),
]

# (username, first_name, last_name, rut, delegacion, rol)
EMPLOYEES = [
    ("diego.molina", "Diego", "Molina Pinto", "10.000.004-4", "Centro", "usuario"),
    ("elena.campas", "Elena", "Campas Mora", "10.000.005-5", "Centro", "usuario"),
    ("gabriela.rojas", "Gabriela", "Rojas Lagos", "10.000.007-7", "Avenida del Mar", "usuario"),
    ("hugo.pizarro", "Hugo", "Pizarro Reyes", "10.000.008-8", "Avenida del Mar", "usuario"),
    ("ines.vera", "Inés", "Vera Salas", "10.000.011-1", "La Antena", "usuario"),
    ("jorge.araya", "Jorge", "Araya Tapia", "10.000.012-2", "Las Compañías", "usuario"),
    ("karen.soto", "Karen", "Soto Núñez", "10.000.013-3", "La Pampa", "usuario"),
    ("luis.cortes", "Luis", "Cortés Ibarra", "10.000.014-4", "Rural", "usuario"),
]

# delegacion -> [(nombre_meta, ponderacion, [(item, unidad, objetivo)])]
GOALS = {
    "Centro": [
        ("Atención territorial y operativos", "60.00", [
            ("Operativos en terreno realizados", "operativos", "12.00"),
            ("Solicitudes vecinales atendidas", "solicitudes", "40.00"),
        ]),
        ("Gestión del espacio público", "40.00", [
            ("Reportes de deterioro gestionados", "reportes", "20.00"),
        ]),
    ],
    "Avenida del Mar": [
        ("Coordinación estacional y espacios públicos", "60.00", [
            ("Reuniones con comercio y residentes", "reuniones", "8.00"),
            ("Inspecciones de espacios públicos", "inspecciones", "15.00"),
        ]),
        ("Seguridad y prevención", "40.00", [
            ("Actividades preventivas realizadas", "actividades", "10.00"),
        ]),
    ],
    "La Antena": [
        ("Fortalecimiento de organizaciones comunitarias", "100.00", [
            ("Capacitaciones a dirigentes", "capacitaciones", "6.00"),
            ("Organizaciones visitadas", "organizaciones", "25.00"),
        ]),
    ],
    "Las Compañías": [
        ("Operativos de salud y bienestar", "70.00", [
            ("Operativos de salud realizados", "operativos", "10.00"),
            ("Vecinos atendidos", "personas", "300.00"),
        ]),
        ("Mantención de áreas verdes", "30.00", [
            ("Plazas intervenidas", "plazas", "8.00"),
        ]),
    ],
    "La Pampa": [
        ("Gestión de reclamos vecinales", "100.00", [
            ("Reclamos resueltos en plazo", "reclamos", "50.00"),
        ]),
    ],
    "Rural": [
        ("Atención a localidades rurales", "100.00", [
            ("Visitas a localidades", "visitas", "14.00"),
            ("Beneficiarios de ayuda en terreno", "personas", "120.00"),
        ]),
    ],
}

# Catálogos: Tipo de Atención -> [(sub atención, descripción)]
ATTENTION_CATALOG = {
    "Atención Social": [
        ("Ayuda social directa", "Entrega de canastas, kits escolares y ayudas puntuales."),
        ("Orientación y derivación", "Orienta al vecino y lo deriva a la red municipal."),
        ("Visita domiciliaria", "Visita para evaluar la situación del hogar."),
    ],
    "Atención Territorial": [
        ("Operativo en terreno", "Jornadas masivas de atención en el barrio."),
        ("Reunión con junta vecinal", "Coordinación con dirigentes vecinales."),
    ],
    "Atención de Espacios Públicos": [
        ("Reporte de deterioro", "Registro de daños en plazas, veredas o luminarias."),
        ("Inspección", "Revisión programada de espacios públicos."),
    ],
    "Atención Comunitaria": [
        ("Capacitación", "Talleres y charlas para organizaciones."),
        ("Actividad preventiva", "Charlas y campañas de prevención."),
    ],
}

# (username_empleado, titulo, estado, dias_al_plazo, nombre_meta, descripcion)
TASKS = [
    ("diego.molina", "Operativo de limpieza calle Cienfuegos", "Completada", -10,
    "Atención territorial y operativos", "Coordinar retiro de escombros."),
    ("diego.molina", "Visita a junta vecinal Centro Histórico", "En Progreso", 5,
    "Atención territorial y operativos", "Levantar requerimientos de alumbrado."),
    ("elena.campas", "Reporte de deterioro en plaza", "Completada", -3,
    "Gestión del espacio público", "Informar a Obras Municipales."),
    ("elena.campas", "Reunión con comerciantes del casco antiguo", "Pendiente", 12,
    "Atención territorial y operativos", "Agendar reunión de coordinación."),
    ("gabriela.rojas", "Reunión con residentes de edificios costeros", "Completada", -7,
    "Coordinación estacional y espacios públicos", "Recoger opinión sobre temporada estival."),
    ("gabriela.rojas", "Inspección de accesos a playa", "En Progreso", 4,
    "Coordinación estacional y espacios públicos", "Revisar señalética y baños públicos."),
    ("hugo.pizarro", "Charla de prevención en borde costero", "Completada", -15,
    "Seguridad y prevención", "Coordinar con Seguridad Ciudadana."),
    # Tarea visible para limitado_demo (usuario de Centro): se asigna a elena
    # aquí y se reasigna a su Employee propio más abajo, cuando ya existe.
    ("elena.campas", "Catastro de luminarias apagadas en Centro", "Pendiente", 7,
    "Gestión del espacio público", "Registrar postes sin luz para derivar a Obras."),
    ("ines.vera", "Taller para dirigentes de La Antena", "En Progreso", 6,
    "Fortalecimiento de organizaciones comunitarias", "Coordinar sede y materiales."),
    ("jorge.araya", "Operativo de salud en Las Compañías", "Pendiente", 9,
    "Operativos de salud y bienestar", "Coordinar con CESFAM."),
    ("karen.soto", "Revisión de reclamos pendientes La Pampa", "Completada", -5,
    "Gestión de reclamos vecinales", "Clasificar reclamos por tipo."),
    ("luis.cortes", "Ruta de visitas a localidades rurales", "En Progreso", 8,
    "Atención a localidades rurales", "Definir calendario de visitas."),
]

# (titulo_tarea, nombre_actividad, dias_ejecucion_relativos)
ACTIVITIES = [
    ("Operativo de limpieza calle Cienfuegos", "Retiro de escombros y limpieza de vereda", -10),
    ("Visita a junta vecinal Centro Histórico", "Reunión con dirigentes vecinales", -1),
    ("Reporte de deterioro en plaza", "Inspección y registro fotográfico del daño", -3),
    ("Reunión con residentes de edificios costeros", "Encuesta de percepción vecinal", -7),
    ("Inspección de accesos a playa", "Revisión de señalética existente", -1),
    ("Charla de prevención en borde costero", "Charla informativa a comerciantes", -15),
    ("Catastro de luminarias apagadas en Centro", "Relevamiento de postes sin iluminación", -1),
]

# (nombre_actividad, url_imagen, validado)
EVIDENCES = [
    ("Retiro de escombros y limpieza de vereda", "https://ejemplo.cl/evidencias/ev-0001.jpg", True),
    ("Inspección y registro fotográfico del daño", "https://ejemplo.cl/evidencias/ev-0002.jpg", False),
    ("Reunión con dirigentes vecinales", "https://ejemplo.cl/evidencias/ev-0003.jpg", False),
    ("Encuesta de percepción vecinal", "https://ejemplo.cl/evidencias/ev-0004.jpg", True),
    ("Revisión de señalética existente", "https://ejemplo.cl/evidencias/ev-0005.jpg", False),
    ("Charla informativa a comerciantes", "https://ejemplo.cl/evidencias/ev-0006.jpg", False),
    ("Relevamiento de postes sin iluminación", "https://ejemplo.cl/evidencias/ev-0007.jpg", False),
]

# (titulo_tarea, username_origen, username_destino, motivo, dias_atras, notas)
REASSIGNMENTS = [
    ("Operativo de limpieza calle Cienfuegos", "diego.molina", "elena.campas", "vacation", 8,
    "La funcionaria asume el operativo durante las vacaciones del titular."),
    ("Reunión con comerciantes del casco antiguo", "elena.campas", "diego.molina", "absence", 3,
    "Derivación por licencia médica del titular."),
    ("Inspección de accesos a playa", "gabriela.rojas", "hugo.pizarro", "other", 2,
    "Apoyo del equipo en la inspección de señalética."),
]

# (username, tipo_beneficio, dias_atras, entregado)
BENEFITS = [
    ("diego.molina", "food_basket", 5, True),
    ("elena.campas", "school_kit", 3, False),
    ("gabriela.rojas", "medical_aid", 1, True),
]


class Command(BaseCommand):
    help = "Carga datos ficticios de demostración sobre los modelos actuales (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--demo-email", default="",
            help="Correo REAL para jefatura_centro (sirve para probar la recuperación de "
                 "contraseña con AWS SES; en modo sandbox debe estar verificado en SES).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        hoy = timezone.localdate()
        User = get_user_model()

        # --- Delegaciones ---
        delegs = {}
        for nombre, desc, color in DELEGATIONS:
            d, _ = Delegation.objects.get_or_create(name=nombre, defaults={"description": desc, "color": color})
            if d.color != color:
                d.color = color
                d.save(update_fields=["color"])
            delegs[nombre] = d

        # --- Usuarios + Funcionarios (Employee) ---
        empleados = {}
        for username, first, last, rut, deleg, rol in EMPLOYEES:
            u, creado = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": f"{username}@ejemplo.cl", "is_staff": True},
            )
            if creado:
                u.set_password(DEMO_PASSWORD)
                u.save()
            emp, _ = Employee.objects.get_or_create(
                user=u, defaults={"rut": rut, "delegation": delegs[deleg], "role": rol},
            )
            if emp.role != rol:
                emp.role = rol
                emp.save(update_fields=["role"])
            empleados[username] = emp

        # --- Catálogos: Tipo de Atención y Sub Atención ---
        for tipo_nombre, subs in ATTENTION_CATALOG.items():
            tipo, _ = AttentionType.objects.get_or_create(
                name=tipo_nombre, defaults={"description": f"Catálogo de {tipo_nombre.lower()}."},
            )
            for sub_nombre, sub_desc in subs:
                AttentionSubtype.objects.get_or_create(
                    attention_type=tipo, name=sub_nombre, defaults={"description": sub_desc},
                )

        # --- Períodos ---
        periodo, _ = Period.objects.get_or_create(
            name="Trimestre Jul-Sep 2026",
            defaults={"start_date": date(2026, 7, 1), "end_date": date(2026, 9, 30),
                    "quarter": 3, "status": "En curso"},
        )
        Period.objects.get_or_create(
            name="Trimestre Abr-Jun 2026",
            defaults={"start_date": date(2026, 4, 1), "end_date": date(2026, 6, 30),
                    "quarter": 2, "status": "Cerrado"},
        )

        # --- Metas institucionales + ítems + cumplimiento ---
        goals = {}
        for deleg, lista in GOALS.items():
            for nombre_meta, pond, items in lista:
                goal, _ = InstitutionalGoal.objects.get_or_create(
                    name=nombre_meta, period=periodo, delegation=delegs[deleg],
                    defaults={"description": f"Meta de {deleg}", "weight": pond},
                )
                goals[nombre_meta] = goal
                Achievement.objects.get_or_create(goal=goal, defaults={"percentage": "45.00"})
                for it_nombre, unidad, objetivo in items:
                    MeasurementItem.objects.get_or_create(
                        goal=goal, name=it_nombre,
                        defaults={"unit_of_measure": unidad, "baseline": "0.00", "target_value": objetivo},
                    )

        # --- Tareas (Task) ---
        tasks = {}
        for username, titulo, estado, dias, meta, desc in TASKS:
            goal = goals[meta]
            plazo = hoy + timedelta(days=dias)
            # el plazo debe caer dentro del período de la meta (lo exige el clean() de TaskForm)
            if not (goal.period.start_date <= plazo <= goal.period.end_date):
                plazo = goal.period.start_date + timedelta(days=15)
            t, _ = Task.objects.get_or_create(
                title=titulo, goal=goal,
                defaults={"description": desc, "due_date": plazo, "status": estado},
            )
            resp = empleados[username]
            if t.assigned_to_id != resp.id:
                t.assigned_to = resp
                t.save(update_fields=["assigned_to"])
            tasks[titulo] = t

        # --- Actividades (Activity) ---
        activities = {}
        for titulo_tarea, nombre_act, dias in ACTIVITIES:
            a, _ = Activity.objects.get_or_create(
                task=tasks[titulo_tarea], name=nombre_act,
                defaults={"execution_date": hoy + timedelta(days=dias)},
            )
            activities[nombre_act] = a

        # --- Evidencias (Evidence) ---
        for nombre_act, url, validado in EVIDENCES:
            Evidence.objects.get_or_create(
                activity=activities[nombre_act],
                defaults={"image_url": url, "is_validated": validado},
            )

        # --- Derivaciones de tareas (TaskReassignment) ---
        # Repartidas entre 2 delegaciones (Centro y Avenida del Mar) para poder
        # comprobar el scoping por delegación en el admin.
        for titulo, origen, destino, motivo, dias, notas in REASSIGNMENTS:
            TaskReassignment.objects.get_or_create(
                task=tasks[titulo],
                original_employee=empleados[origen],
                reassigned_employee=empleados[destino],
                defaults={
                    "reason": motivo,
                    "reassigned_at": timezone.now() - timedelta(days=dias),
                    "notes": notas,
                },
            )

        # --- Beneficios (Benefit) ---
        # delivery_area debe coincidir con la delegación del funcionario (lo valida clean())
        for username, tipo, dias, entregado in BENEFITS:
            emp = empleados[username]
            Benefit.objects.get_or_create(
                employee=emp, benefit_type=tipo,
                defaults={
                    "delivery_area": emp.delegation,
                    "delivered_at": (timezone.now() - timedelta(days=dias)) if entregado else None,
                    "delivered": entregado,
                },
            )

        # --- Usuarios del Django Admin (administrador y limitado) ---
        admin_u, _ = User.objects.get_or_create(
            username=ADMIN_USER, defaults={"email": f"{ADMIN_USER}@ejemplo.cl"},
        )
        admin_u.is_staff = admin_u.is_superuser = True
        admin_u.set_password(DEMO_PASSWORD)
        admin_u.save()

        lim_u, _ = User.objects.get_or_create(
            username=LIMITED_USER,
            defaults={"first_name": "Usuario", "last_name": "Limitado", "email": f"{LIMITED_USER}@ejemplo.cl"},
        )
        lim_u.is_staff, lim_u.is_superuser = True, False
        lim_u.set_password(DEMO_PASSWORD)
        lim_u.save()
        # el usuario limitado también necesita su propio Employee, para que
        # TaskAdmin.get_queryset() pueda filtrar por su delegación (scoping)
        lim_emp, _ = Employee.objects.get_or_create(
            user=lim_u, defaults={"rut": "10.000.099-9", "delegation": delegs["Centro"], "role": "usuario"},
        )
        if lim_emp.role != "usuario":
            lim_emp.role = "usuario"
            lim_emp.save(update_fields=["role"])
        permisos = Permission.objects.filter(
            content_type__app_label="operaciones",
            codename__in=["view_task", "change_task", "view_activity", "view_evidence", "change_evidence"],
        )
        lim_u.user_permissions.set(permisos)
        # Tarea propia del usuario limitado: se reasigna a su Employee para
        # poder probar el scoping de Usuario (assigned_to propio).
        t_lim = tasks.get("Catastro de luminarias apagadas en Centro")
        if t_lim is not None and t_lim.assigned_to_id != lim_emp.id:
            t_lim.assigned_to = lim_emp
            t_lim.save(update_fields=["assigned_to"])

        # --- Jefatura de delegación (Centro): ve todo lo de su delegación ---
        boss_u, _ = User.objects.get_or_create(
            username=BOSS_USER,
            defaults={"first_name": "Jefatura", "last_name": "Centro", "email": f"{BOSS_USER}@ejemplo.cl", "is_staff": True},
        )
        boss_u.is_staff = True
        boss_u.is_superuser = False
        boss_u.set_password(DEMO_PASSWORD)
        boss_u.save()
        boss_emp, _ = Employee.objects.get_or_create(
            user=boss_u, defaults={"rut": "10.000.100-2", "delegation": delegs["Centro"], "role": "jefatura"},
        )
        if boss_emp.role != "jefatura" or boss_emp.delegation_id != delegs["Centro"].id:
            boss_emp.role, boss_emp.delegation = "jefatura", delegs["Centro"]
            boss_emp.save(update_fields=["role", "delegation"])
        boss_u.user_permissions.set(permisos)
        if options.get("demo_email"):
            boss_u.email = options["demo_email"]
            boss_u.save(update_fields=["email"])

        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados."))
        self.stdout.write(f"  Administrador:  {ADMIN_USER} / {DEMO_PASSWORD}")
        self.stdout.write(f"  Usuario limitado (delegación Centro): {LIMITED_USER} / {DEMO_PASSWORD}")
        self.stdout.write(f"  Jefatura (delegación Centro): {BOSS_USER} / {DEMO_PASSWORD}")