# Checklist de entrega

Lista de verificación del repositorio antes de la revisión. Marca cada ítem al
confirmarlo; los que no apliquen se indican explícitamente.

## Repositorio

- [ ] No hay `.env` ni `.venv/` ni `venv/` versionados (`.gitignore` los excluye).
- [ ] `db.sqlite3` y `staticfiles/` no están versionados.
- [ ] Las ramas tienen nombres descriptivos (p. ej. `feature/ui-p4-motor-mantenedores`).
- [ ] Los commits son comprensibles (mensajes cortos que describen el cambio).
- [ ] Existe una etiqueta de entrega (`git tag`) apuntando al commit revisado.
- [ ] Se informa el hash del commit de entrega en esta misma hoja.

## Verificación técnica (ejecutada)

- [ ] `python manage.py check` → sin errores.
- [ ] `python manage.py makemigrations --check --dry-run` → sin cambios pendientes.
- [ ] `python manage.py test` → toda la suite en verde (y en < 2 minutos).
- [ ] `python manage.py collectstatic --dry-run --noinput` → sin errores.

## Documentación

- [ ] `README.md`: instalación desde cero, usuarios demo, mapa de URLs, matriz de
      permisos, configuración del correo (incluido el log simulado), despliegue
      EC2 y tabla "Operativo / Simulado / Pendiente".
- [ ] `docs/pruebas/pruebas_funcionales.md`: 50 casos pre-cargados con estado
      "pendiente de ejecución" (sin resultados inventados).
- [ ] `docs/pruebas/pruebas_estres.md`: umbrales definidos y tabla de resultados
      vacía (Locust sin ejecutar).
- [ ] `requirements-dev.txt` con la dependencia de desarrollo (Locust).

## Seguridad (revisada)

- [ ] CSRF en todos los POST; ninguna acción destructiva por GET.
- [ ] Sin hashes ni contraseñas en exportaciones; autoescape sin `|safe`
      injustificado; sin SQL crudo.
- [ ] `DEBUG`, `ALLOWED_HOSTS` y `SECRET_KEY` solo por `.env`.
- [ ] Errores sin trazas para el usuario; cabeceras `X-Frame-Options` y `nosniff`;
      cookie de sesión `HttpOnly`.
- [ ] `SESSION_COOKIE_SECURE` y `SECURE_SSL_REDIRECT` desactivados mientras el
      servidor sea HTTP (se activan al pasar a HTTPS).

## Datos de la entrega

- Rama: `feature/ui-p4-motor-mantenedores`
- Hash del commit de entrega: _(completar al confirmar)_
- Etiqueta de entrega: _(completar al etiquetar)_
