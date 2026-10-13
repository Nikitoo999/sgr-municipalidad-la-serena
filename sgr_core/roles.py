"""Constantes y matriz de permisos de roles (módulo puro, sin Django ORM).

Este módulo puede ser importado desde migraciones de datos y desde seed_demo:
no importa modelos, solo constantes. La creación idempotente de los 4 roles
base recibe las clases de modelo como argumentos (reales u históricas).
"""

MODULES = (
    ('delegations', 'Delegaciones'),
    ('roles', 'Roles'),
    ('users', 'Usuarios'),
    ('items', 'Ítems de medición'),
    ('attention_types', 'Tipos de atención'),
    ('attention_subtypes', 'Subtipos de atención'),
    ('attentions', 'Atenciones'),
)

ACTIONS = (
    ('view', 'Ver'),
    ('create', 'Crear'),
    ('edit', 'Editar'),
    ('delete', 'Eliminar'),
    ('export', 'Exportar'),
)

SCOPES = (
    ('all', 'Todas las delegaciones'),
    ('authorized', 'Delegaciones autorizadas'),
    ('own_delegation', 'Su delegación'),
    ('own_records', 'Solo registros propios'),
)

# Rango derivado del alcance: mayor rango = mayor autoridad.
SCOPE_RANKS = {
    'all': 3,
    'authorized': 2,
    'own_delegation': 1,
    'own_records': 0,
}

MODULE_KEYS = tuple(key for key, _ in MODULES)
ACTION_KEYS = tuple(key for key, _ in ACTIONS)
ALL_ACTIONS = ACTION_KEYS                    # view, create, edit, delete, export
STD_ACTIONS = ('view', 'create', 'edit', 'export')

# Mapa nombre de delegación → código (fila existente: se resuelve en la
# migración de datos; delegaciones nuevas se crean directamente con su código).
DELEGATION_CODE_MAP = {
    'Centro': 'DEL01',
    'Avenida del Mar': 'DEL02',
    'La Antena': 'DEL03',
    'La Antena-La Florida': 'DEL03',
    'Las Compañías': 'DEL04',
    'La Pampa': 'DEL05',
    'Rural': 'DEL06',
}

RENAMED_DELEGATIONS = {
    'La Antena': 'La Antena-La Florida',
}

# Matriz base de permisos (claves en inglés) según el contexto común.
BASE_ROLES = (
    {
        'code': 'ROL01',
        'name': 'Superadministrador',
        'description': 'Administra delegaciones, roles, usuarios y catálogos de todo el sistema.',
        'scope': 'all',
        'is_system': True,
        'permissions': {module: ALL_ACTIONS for module in MODULE_KEYS},
    },
    {
        'code': 'ROL02',
        'name': 'Coordinador',
        'description': 'Gestiona usuarios, catálogos y atenciones de varias delegaciones autorizadas.',
        'scope': 'authorized',
        'is_system': False,
        'permissions': {
            'users': STD_ACTIONS,
            'items': STD_ACTIONS,
            'attention_types': STD_ACTIONS,
            'attention_subtypes': STD_ACTIONS,
            'attentions': STD_ACTIONS,
        },
    },
    {
        'code': 'ROL03',
        'name': 'Delegado municipal',
        'description': 'Administra a su equipo y las atenciones de su delegación.',
        'scope': 'own_delegation',
        'is_system': False,
        'permissions': {
            'users': STD_ACTIONS,
            'items': ('view', 'export'),
            'attentions': STD_ACTIONS,
        },
    },
    {
        'code': 'ROL04',
        'name': 'Funcionario',
        'description': 'Ingresa atenciones y consulta las que registró.',
        'scope': 'own_records',
        'is_system': False,
        'permissions': {
            'attentions': ('view', 'create', 'export'),
        },
    },
)


def ensure_base_roles(role_cls, permission_cls):
    """Crea/actualiza de forma idempotente los 4 roles base y su matriz.

    Funciona con modelos reales o históricos (migraciones de datos).
    El estado (Activo/Inactivo) de un rol existente NO se modifica: solo se
    crean roles ausentes y se sincronizan los campos canónicos y permisos.
    """
    for spec in BASE_ROLES:
        role, _created = role_cls.objects.get_or_create(
            code=spec['code'],
            defaults={
                'name': spec['name'],
                'description': spec['description'],
                'scope': spec['scope'],
                'is_system': spec['is_system'],
            },
        )
        changed = False
        for field in ('name', 'description', 'scope', 'is_system'):
            if getattr(role, field) != spec[field]:
                setattr(role, field, spec[field])
                changed = True
        if changed:
            role.save()

        wanted = {
            (module, action)
            for module, actions in spec['permissions'].items()
            for action in actions
        }
        existing = set(
            permission_cls.objects.filter(role=role).values_list('module', 'action')
        )
        for module, action in sorted(wanted - existing):
            permission_cls.objects.get_or_create(role=role, module=module, action=action)
        for module, action in sorted(existing - wanted):
            permission_cls.objects.filter(role=role, module=module, action=action).delete()
    return role_cls.objects.filter(code__in=[s['code'] for s in BASE_ROLES])