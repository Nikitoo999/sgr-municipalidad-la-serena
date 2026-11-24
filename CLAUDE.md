# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

SGR (Sistema de Gestión de Resultados) for the Municipalidad de La Serena: a Django 5.2 server-rendered portal with Channels/Daphne for WebSockets. Code identifiers are in English, while UI text, docstrings, comments, URL slugs and DB table names (`db_table`) are in Spanish (es-CL). Keep that split when adding code.

## Commands

```bash
pip install -r requirements.txt          # requirements-dev.txt adds locust
cp .env.example .env                     # SQLite by default; MariaDB via DB_ENGINE/DB_* vars
python manage.py migrate
python manage.py seed_demo               # idempotent demo data; all demo users use password Demo2026!
python manage.py runserver               # Daphne is installed, so runserver is ASGI
daphne config.asgi:application --bind 127.0.0.1 --port 8000   # production-style ASGI

python manage.py test                                    # full suite (Django test runner, no pytest)
python manage.py test portal.tests.test_crud_users       # one module
python manage.py test portal.tests.test_crud_users.SomeTestCase.test_method   # one test
python manage.py makemigrations --check --dry-run        # detect missing migrations
python manage.py generar_modelo_docs                     # regenerate docs/db/modelo_entidad_relacion.md from models
```

Other seed commands live in `operaciones/management/commands/` (`seed_cargos`, `seed_catalogo_atenciones`, `seed_metas_cargos`, `seed_organizaciones`). Stress tests: `tests/stress/` (Locust, see `docs/pruebas/pruebas_estres.md`).

`CHANNEL_LAYERS` uses `channels_redis` with `REDIS_URL` (default `redis://127.0.0.1:6379/0`). Running Daphne with live WebSockets, and the realtime consumer tests in `portal/tests/test_realtime.py`, needs a reachable Redis. The README still says `InMemoryChannelLayer`, but that is out of date.

## Architecture

Three apps:

- **`sgr_core`**: domain catalog: `Delegation`, `Role`, `RolePermission`, `Position`, attention types/subtypes, project items, goals, organizations. `sgr_core/roles.py` is a **pure module with no ORM imports**: `MODULES`, `ACTIONS`, `SCOPES`, `SCOPE_RANKS` and `ensure_base_roles(role_cls, permission_cls)`, which takes model classes as arguments so data migrations (historical models) and `seed_demo` can both use it.
- **`operaciones`**: operational data: `Employee` (OneToOne to `auth.User`, holds role, delegation, `authorized_delegations`), `Attention`, `Neighbor`, tasks/activities/evidence, `TubeEntry`, feedback. Business rules for attentions (daily cap of 7 per employee, max 3 follow-ups, weekly closure per delegation, `counts_for_score`) are centralized in `operaciones/rules.py`. Score and compliance calculations are in `operaciones/calculos.py`. Reuse these modules instead of reimplementing the rules in views and forms.
- **`portal`**: everything web: auth, views, templates, static, WebSockets, audit log.

Most models inherit `sgr_core.models.BaseModel` (`created_at`/`updated_at`/`deleted_at`). The schema comes from the Django models and migrations. The SQL under `database/legacy/` is historical only.

### Authorization (`portal/access.py`)

Every "who can see/do what" decision goes through this module. Do not check roles ad hoc in views.
- `get_role(user)` returns an `AccessRole`. A superuser without `Employee` gets a virtual superadmin role. A non-superuser without `Employee`, or a user whose role is inactive, gets `None` (no access).
- Four base roles ranked by scope: superadmin=3, coordinator=2, delegate=1, staff (funcionario)=0. Users cannot see or edit users of equal or higher rank, and cannot assign a role of equal or higher rank (`can_assign_role`). Only the superadmin deletes.
- `has_permission(user, module, action)` checks against `RolePermission` (module keys come from `sgr_core.roles.MODULES`).
- `allowed_delegations` / `get_active_delegation` / `set_active_delegation`: a coordinator picks an "active delegation" stored in the session, validated server-side. `ALL` is a special value.
- Access info is cached per request on `request._sgr_access_info`.
- Views use `ModulePermissionMixin` / `permission_required` (403 on denial). Relevant actions are logged through `portal.audit.audit()`.

### Declarative CRUD engine (`portal/crud/`)

The maintenance modules (delegations, roles, users, items, attention_types, attention_subtypes, attentions) are declared once as a `ModuleConfig` (columns, filters, sort keys, page sizes, grammatical gender for titles) and registered with `register_module()` in their own file. `portal/crud/urls.py` imports each module to register it, then generates `/<slug>/`, `nuevo/`, `<pk>/`, `<pk>/editar/`, `<pk>/eliminar/` (POST only) and `exportar/` (Excel via openpyxl) routes, handled by the generic views in `portal/crud/views.py` and the shared templates `portal/templates/portal/crud/list.html` and `form.html`. Attentions extends this with custom views (follow-ups, weekly closure, neighbor lookup). To add a module:
1. Add its key to `sgr_core.roles.MODULES`, plus a data migration for permissions if needed.
2. Add its label, icon and URL name in `portal/modules.py`, which drives the navigation through `portal/context_processors.sgr_context`.
3. Write the `ModuleConfig` and register it.

The non-CRUD pages (home, agenda, goals, compliance, reports, tubes) are individual `*_views.py` files in `portal/`.

### Realtime

`config/asgi.py` routes WebSockets through `AllowedHostsOriginValidator` + `AuthMiddlewareStack` to `portal/routing.py`:
- `ws/chat/<delegation_code>/`: delegation chat.
- `ws/atenciones/<delegation_code>/`: live attention notices.

Consumers in `portal/consumers.py` check delegation scope (`_user_can_access_delegation`). Creating an attention broadcasts `attention_created` to the groups `atenciones_<code>` and `atenciones_ALL` (`portal/crud/attentions.py`). The frontend side lives in `portal/static/portal/js/sgr.js`.

## Conventions and gotchas

- **Tests:** import shared fixtures from `portal/tests/helpers.py` (`ensure_roles`, `make_delegation`, `make_user`, `make_employee`, `DEMO_PASSWORD`). Decorate view tests with `@override_settings(STORAGES=TEST_STORAGES)`, because production uses whitenoise's `CompressedManifestStaticFilesStorage`, which fails on `{% static %}` without `collectstatic`. Helper modules must not define `test_*` functions. `docs/entrega.md` expects the full suite to stay green and run in under 2 minutes.
- Every data-changing action is a POST with CSRF. Delete, logout and switching delegation have no GET route.
- Authentication uses `portal.backends.EmailOrUsernameBackend` (username or email, case-insensitive). Login locks for 10 minutes after 5 failed attempts.
- Email defaults to the console backend: password-reset codes are printed to the server log.
- Excel exports must never include passwords or hashes.
- MariaDB uses `utf8mb4_unicode_ci`. Uniqueness of codes and emails is case-insensitive and validated in forms, relying on that collation.
- Production runs on EC2 with systemd running Daphne (`deploy/sgr.service`), with `DEBUG=False`.
