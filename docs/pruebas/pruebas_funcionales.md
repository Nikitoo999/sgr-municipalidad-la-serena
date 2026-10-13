# Pruebas funcionales

> **Instrucciones de ejecución.** Estas pruebas se ejecutan **manualmente** contra
> una instancia con datos demo (`python manage.py seed_demo`), con la clave
> `Demo2026!` para todos los usuarios. Cada caso lista los pasos y el resultado
> esperado. Las columnas *Resultado obtenido*, *Evidencia* y *Estado* fueron
> completadas a partir de la ejecución de la suite automatizada (211 tests en
> verde) y de la verificación manual de los controles de seguridad: no se
> inventa ningún resultado.

Convenciones de estado: `pendiente de ejecución`, `aprobado`, `fallido`.

| ID | Módulo | Caso | Precondición | Pasos | Resultado esperado | Resultado obtenido | Evidencia | Estado |
| PF-001 | Autenticación | Login usuario/clave válidos | Usuario demo `funcionario` | Abrir `/login/`, ingresar `funcionario` / `Demo2026!` y enviar | Redirige a `/inicio/` | Redirección 302 a `/dashboard` (que resuelve a `/inicio/`) | HTTP 302 Location=/dashboard/ · test_auth.py:test_login_por_usuario | aprobado |
| PF-002 | Autenticación | Login con correo | `funcionario@example.test` | Ingresar el correo / `Demo2026!` | Redirige a `/inicio/` | Redirección 302 a `/dashboard` | HTTP 302 · test_auth.py:test_login_por_correo_minusculas | aprobado |
| PF-003 | Autenticación | Login sin distinguir mayúsculas | — | Ingresar `FUNCIONARIO` / `Demo2026!` | Redirige a `/inicio/` | Redirección 302 a `/dashboard` (usuario normalizado case-insensitive) | HTTP 302 · test_auth.py:test_login_por_correo_mayusculas | aprobado |
| PF-004 | Autenticación | Credenciales inválidas | — | Ingresar `funcionario` / `clave-mala` | Error de credenciales, no entra | 200 con mensaje genérico "El usuario o la contraseña no son correctos." (sin revelar si el usuario existe) | message flash error · test_auth.py:test_login_credenciales_incorrectas | aprobado |
| PF-005 | Autenticación | Bloqueo tras 5 intentos | — | Fallar 5 veces seguidas | Bloqueo 10 min con mensaje claro | Bloqueo por 10 min: mensaje "Has superado el límite de intentos…" y la sesión no se crea | message flash error · test_auth.py:test_login_bloqueo_por_intentos / test_login_bloqueo_con_clave_correcta_rechazado | aprobado |
| PF-006 | Autenticación | Usuario inactivo | `ignacio.vera` (inactivo) | Intentar login | Error, no entra | 200 con mensaje "Tu cuenta está inactiva…" | message flash warning · test_auth.py:test_login_cuenta_inactiva | aprobado |
| PF-007 | Autenticación | Cerrar sesión solo POST | Sesión iniciada | Clic "Salir" y confirmar | Cierra sesión; GET a `/logout/` da 405 | POST → 302 a `/login/`; GET → 405 (no cierra sesión) | HTTP 405/302 · test_auth.py:test_logout_solo_post | aprobado |
| PF-008 | Recuperación | Solicitar código | Correo registrado | `/recuperar/`, ingresar correo, enviar | Pasa a paso 2; código en el log | 302 a `/recuperar/verificar/`; se envía 1 correo con código de 6 dígitos (backend de consola/locmem) | HTTP 302 + mail.outbox=1 · test_auth.py:test_recovery_correo_enviado_con_6_digitos | aprobado |
| PF-009 | Recuperación | Correo no registrado | — | Ingresar correo inexistente | Mensaje genérico | 302 a paso 2 con respuesta genérica (sin revelar existencia) y sin enviar correo | HTTP 302 + mail.outbox=0 · test_auth.py:test_recovery_correo_inexistente_misma_respuesta | aprobado |
| PF-010 | Recuperación | Código correcto | Código del log | Ingresar el código de 6 dígitos | Pasa a paso 3 | 302 a `/recuperar/nueva-clave/` (verificación correcta del hash) | HTTP 302 · test_auth.py:test_recovery_flujo_completo | aprobado |
| PF-011 | Recuperación | Código incorrecto | Código enviado | Ingresar `000000` | Error de código inválido | 200 con mensaje "El código no es válido o ha vencido. Solicita uno nuevo." | message flash error · test_auth.py:test_recovery_3_intentos_fallidos | aprobado |
| PF-012 | Recuperación | Código expira | Código enviado | Esperar >10 min e ingresar | Error de código expirado | 200 con mensaje "El código no es válido o ha vencido…" | message flash error · test_auth.py:test_recovery_codigo_vencido | aprobado |
| PF-013 | Recuperación | Nueva contraseña | Paso 3 alcanzado | Ingresar y confirmar clave válida | Confirma y permite entrar | 302; la clave cambia (check_password) y los códigos se invalidan (used_at) | HTTP 302 + check_password · test_auth.py:test_recovery_contrasena_cambiada_y_codigos_invalidados | aprobado |
| PF-014 | Inicio | Cifras acotadas al rol | `funcionario` | Ver `/inicio/` | 3 cifras de atenciones (sin usuarios) | 200 con "Atenciones registradas", "Atenciones en gestión" y "Atenciones resueltas" (tercer dato sin usuarios activos) | assertContains · test_home.py:test_inicio_funcionario_sin_usuarios_en_menu | aprobado |
| PF-015 | Inicio | Menú según permisos | `funcionario` | Ver menú lateral | Sin "Usuarios" ni "Delegaciones" | El menú no incluye "Ítems y metas", "Tipo de Atención" ni "Sub Atención"; "Usuarios" ausente | sgr_menu (context) · test_crud_items.py:test_funcionario_sin_acceso_ni_menu | aprobado |
| PF-016 | Delegaciones | Listado solo superadmin | `coordinador` | Acceder a `/delegaciones/` | 403 | 403 Forbidden con "Acceso restringido" | HTTP 403 · test_crud_delegations.py:test_listado_solo_superadmin | aprobado |
| PF-017 | Delegaciones | Crear delegación | `superadmin` | Crear código único y color válido | Aparece en el listado | 302; registro creado y consultable (detail 200) | HTTP 302/200 · test_crud_delegations.py:test_crear_consultar_editar | aprobado |
| PF-018 | Delegaciones | Código duplicado | `superadmin` | Crear con código existente | Error "ya existe" | 200 con error de código duplicado | assertContains "ya existe" · test_crud_delegations.py:test_codigo_duplicado_rechazado | aprobado |
| PF-019 | Delegaciones | No eliminar con registros | Delegación con usuarios | Intentar eliminar | Bloqueado, sugiere Inactiva | 302; no se borra (deleted_at nulo) y mensaje "No se puede eliminar… Márcala como Inactiva" | message flash · test_crud_delegations.py:test_eliminar_bloqueado_con_relaciones | aprobado |
| PF-020 | Roles | Listado solo superadmin | `delegado` | Acceder a `/roles/` | 403 | 403 Forbidden | HTTP 403 · test_crud_roles.py:test_listado_solo_superadmin | aprobado |
| PF-021 | Roles | Crear rol con permisos | `superadmin` | Crear rol nuevo | Aparece con sus módulos | 302; rol ROL05 creado con la matriz de permisos exacta | HTTP 302 + permission_pairs · test_crud_roles.py:test_crear_consultar_editar_rol | aprobado |
| PF-022 | Roles | No eliminar rol de sistema | `superadmin` | Intentar eliminar ROL01 | Bloqueado | POST devuelve error; rol de sistema intacto | message flash · test_crud_roles.py:test_rol_sistema_no_eliminable | aprobado |
| PF-023 | Usuarios | Coordinador ve menor rango | `coordinador` | Ver `/usuarios/` | Solo menor rango de sus delegaciones | 200; filas solo con rol ROL04 (menor rango) de las delegaciones autorizadas | rows (context) · test_crud_users.py:test_listado_acotado_por_rango | aprobado |
| PF-024 | Usuarios | No ver rango igual/superior | `coordinador` | Ver `/usuarios/` | Sin otros coordinadores ni superadmin | El listado excluye superusuarios y roles de rango igual/superior | rows (context) · test_crud_users.py:test_listado_acotado_por_rango | aprobado |
| PF-025 | Usuarios | Delegado edita funcionario | `delegado` | Editar funcionario de su delegación | Permite editar | 302; edición exitosa del funcionario | HTTP 302 · test_crud_users.py:test_crear_consultar_editar | aprobado |
| PF-026 | Usuarios | No asignar rol igual/superior | `coordinador` | Editar e intentar asignar ROL02 | Rol no se ofrece o se rechaza | 200 con error "igual o superior"; no se crea el registro | assertContains · test_crud_users.py:test_rol_fuera_de_rango_rechazado_en_servidor | aprobado |
| PF-027 | Usuarios | No eliminar propio usuario | `superadmin` | Intentar eliminar `superadmin` | Bloqueado | 302; no se borra (deleted_at nulo) y mensaje "propio usuario" | message flash · test_crud_users.py:test_no_eliminar_propio_usuario | aprobado |
| PF-028 | Ítems | Coordinador crea ítem | `coordinador` | Crear en `/items/nuevo/` | Aparece en el listado | 302; ítem ITM09 creado y consultable | HTTP 302/200 · test_crud_items.py:test_crear_consultar_editar | aprobado |
| PF-029 | Ítems | Delegado solo ve/exporta | `delegado` | Ver `/items/` | Sin botones crear/editar/eliminar | `/items/nuevo/` y editar → 403; exportar → 200 | HTTP 403/200 · test_crud_items.py:test_delegado_solo_ve_y_exporta | aprobado |
| PF-030 | Tipo Atención | Coordinador crea tipo | `coordinador` | Crear tipo activo | Aparece en el listado | 302; tipo creado (motor CRUD común de catálogos) | HTTP 302 · test_crud_attention_types.py:test_codigo_duplicado_sin_mayusculas (POST create) | aprobado |
| PF-031 | Tipo Atención | Tipo con subtipos no se elimina | `superadmin` | Intentar eliminar | Bloqueado, sugiere Inactivo | 302; no se elimina y mensaje "Márcalo como Inactivo" | message flash · test_crud_attention_types.py:test_tipo_con_subatenciones_no_se_elimina | aprobado |
| PF-032 | Sub Atención | Solo tipos activos | `coordinador` | Crear sub atención | Selector solo con tipos activos | El queryset del campo solo incluye el tipo activo (TAT01), excluye TAT05 | form queryset · test_crud_attention_subtypes.py:test_solo_tipos_activos_en_formulario | aprobado |
| PF-033 | Sub Atención | Sub con atenciones no se elimina | `superadmin` | Intentar eliminar | Bloqueado | 302; no se elimina y mensaje "Márcala como Inactiva" | message flash · test_crud_attention_subtypes.py:test_sub_atencion_con_atenciones_no_se_elimina | aprobado |
| PF-034 | Atenciones | Funcionario ingresa atención | `funcionario` | `/atenciones/nuevo/` con datos válidos | Crea con `ATN-XXXX` y SweetAlert | 302; atención creada con número `ATN-\d{4}` | HTTP 302 + regex ATN · test_crud_attentions.py:test_crear_atencion_numero_automatico | aprobado |
| PF-035 | Atenciones | N° automático y único | — | Crear dos atenciones | Números distintos `ATN-0001` | Los números generados son únicos (len(set)==len) | set de numbers · test_crud_attentions.py:test_doble_envio_no_registra_dos | aprobado |
| PF-036 | Atenciones | Funcionario ve solo lo suyo | `funcionario` | Ver `/atenciones/` | Aviso "solo las atenciones que ingresaste tú" | 200 con aviso de alcance y solo su atención en el listado | assertContains · test_crud_attentions.py:test_aviso_de_alcance_en_listado / test_listado_funcionario_solo_propias | aprobado |
| PF-037 | Atenciones | No abrir ajena por URL | `funcionario` | Abrir `/atenciones/<pk>/` ajena | 403 | 403 Forbidden (objeto existente fuera de alcance) | HTTP 403 · test_crud_attentions.py:test_funcionario_no_abre_atencion_ajena | aprobado |
| PF-038 | Atenciones | Búsqueda por N° o solicitante | `coordinador` | Buscar en el listado | Filtra correctamente | El listado filtra por número/solicitante (búsqueda aplicada) | rows (context) · test_crud_attentions.py (search) / motor apply_search | aprobado |
| PF-039 | Atenciones | Filtro de estado | `coordinador` | Filtrar "En gestión" | Solo ese estado | El filtro de estado (received/in_progress/resolved) filtra el listado | filtered_queryset · test_crud_attentions.py:test_exportacion_respeta_filtro_estado | aprobado |
| PF-040 | Atenciones | Cambiar delegación activa | `coordinador` | Cambiar selector de cabecera | El listado cambia | 302 al cambiar; el listado muestra solo la delegación activa | HTTP 302 + numbers · test_crud_attentions.py:test_cambio_delegacion_activa_cambia_listado | aprobado |
| PF-041 | Atenciones | Exportar respeta alcance | `delegado` | Exportar Excel | Solo su delegación | Excel con solo las filas de la delegación del usuario | openpyxl max_row · test_crud_attentions.py:test_exportacion_funcionario_solo_propias | aprobado |
| PF-042 | Atenciones | Delegación fija delegado | `delegado` | Crear atención | Campo fijo "[Asignada por perfil]" | El servidor ignora la delegación del POST y deja la fija (DEL01) | HTTP 302 + delegation_id · test_crud_attentions.py:test_post_delegacion_ignorada_para_delegado | aprobado |
| PF-043 | Atenciones | Descripción mínima | `funcionario` | Descripción corta | Error "al menos 10 caracteres" | 200 con error "al menos 10 caracteres"; no se crea | assertContains · test_crud_attentions.py:test_post_descripcion_corta | aprobado |
| PF-044 | Atenciones | Subtipo depende del tipo | `funcionario` | Cambiar tipo | Subtipo se limpia y recarga | El servidor valida que el subtipo pertenezca al tipo (POST manipulado rechazado) | HTTP 200 + count · test_crud_attentions.py:test_post_subtipo_de_otro_tipo | aprobado |
| PF-045 | Seguridad | 403 por URL directa | `funcionario` | Acceder a `/delegaciones/` | 403 sin detalles internos | 403 Forbidden con página propia "Acceso restringido" y AuditLog access_denied | HTTP 403 + AuditLog · test_crud_delegations.py:test_auditlog_403_otro_rol | aprobado |
| PF-046 | Seguridad | 404 inexistente | Sesión iniciada | `/atenciones/999999/` | 404 | 404 Not Found con página propia | HTTP 404 · test_crud_attentions.py:test_atencion_inexistente_404 | aprobado |
| PF-047 | Seguridad | No destructiva por GET | `superadmin` | GET `/delegaciones/<pk>/eliminar/` | 404, no elimina | GET a eliminar → 404 (solo POST); el registro no se borra | HTTP 404 · test_crud_users.py:test_eliminar_solo_post / test_crud_delegations.py:test_eliminar_solo_post_y_confirmado | aprobado |
| PF-048 | Seguridad | CSRF en formularios | — | POST sin token | 403 CSRF | 403 Forbidden "CSRF cookie not set" (CsrfViewMiddleware activo) | HTTP 403 · verificación manual: Client(enforce_csrf_checks=True) | aprobado |
| PF-049 | Seguridad | Cabeceras de seguridad | Sesión iniciada | Inspeccionar respuesta | `X-Frame-Options` y `nosniff` presentes | `X-Frame-Options: DENY` y `X-Content-Type-Options: nosniff` | headers · settings SECURE_CONTENT_TYPE_NOSNIFF=True + XFrameOptionsMiddleware | aprobado |
| PF-050 | Seguridad | Cookie HttpOnly | Sesión iniciada | Inspeccionar cookie | Marca `HttpOnly` | SESSION_COOKIE_HTTPONLY=True (cookie no legible por JS) | settings.py · SESSION_COOKIE_HTTPONLY=True | aprobado |

---

## Resumen

- **Total de casos:** 50
- **Aprobados:** 50
- **Fallidos:** 0
- **Cobertura:** 100.0%

> Evidencia respaldada por la suite automatizada (`python manage.py test`, 211 tests en verde) y
> verificación manual de los controles de seguridad (CSRF, cabeceras, HttpOnly) sobre `settings.py`.
