# Pruebas funcionales

> **Instrucciones de ejecución.** Estas pruebas se ejecutan **manualmente** contra
> una instancia con datos demo (`python manage.py seed_demo`), con la clave
> `Demo2026!` para todos los usuarios. Cada caso lista los pasos y el resultado
> esperado; las columnas *Resultado obtenido*, *Evidencia* y *Estado* quedan
> **vacías** hasta que se ejecuten: no se inventa ningún resultado.

Convenciones de estado: `pendiente de ejecución`, `aprobado`, `fallido`.

| ID | Módulo | Caso | Precondición | Pasos | Resultado esperado | Resultado obtenido | Evidencia | Estado |
|---|---|---|---|---|---|---|---|---|
| PF-001 | Autenticación | Login usuario/clave válidos | Usuario demo `funcionario` | Abrir `/login/`, ingresar `funcionario` / `Demo2026!` y enviar | Redirige a `/inicio/` |  |  | pendiente de ejecución |
| PF-002 | Autenticación | Login con correo | `funcionario@example.test` | Ingresar el correo / `Demo2026!` | Redirige a `/inicio/` |  |  | pendiente de ejecución |
| PF-003 | Autenticación | Login sin distinguir mayúsculas | — | Ingresar `FUNCIONARIO` / `Demo2026!` | Redirige a `/inicio/` |  |  | pendiente de ejecución |
| PF-004 | Autenticación | Credenciales inválidas | — | Ingresar `funcionario` / `clave-mala` | Error de credenciales, no entra |  |  | pendiente de ejecución |
| PF-005 | Autenticación | Bloqueo tras 5 intentos | — | Fallar 5 veces seguidas | Bloqueo 10 min con mensaje claro |  |  | pendiente de ejecución |
| PF-006 | Autenticación | Usuario inactivo | `ignacio.vera` (inactivo) | Intentar login | Error, no entra |  |  | pendiente de ejecución |
| PF-007 | Autenticación | Cerrar sesión solo POST | Sesión iniciada | Clic "Salir" y confirmar | Cierra sesión; GET a `/logout/` da 405 |  |  | pendiente de ejecución |
| PF-008 | Recuperación | Solicitar código | Correo registrado | `/recuperar/`, ingresar correo, enviar | Pasa a paso 2; código en el log |  |  | pendiente de ejecución |
| PF-009 | Recuperación | Correo no registrado | — | Ingresar correo inexistente | Mensaje genérico |  |  | pendiente de ejecución |
| PF-010 | Recuperación | Código correcto | Código del log | Ingresar el código de 6 dígitos | Pasa a paso 3 |  |  | pendiente de ejecución |
| PF-011 | Recuperación | Código incorrecto | Código enviado | Ingresar `000000` | Error de código inválido |  |  | pendiente de ejecución |
| PF-012 | Recuperación | Código expira | Código enviado | Esperar >10 min e ingresar | Error de código expirado |  |  | pendiente de ejecución |
| PF-013 | Recuperación | Nueva contraseña | Paso 3 alcanzado | Ingresar y confirmar clave válida | Confirma y permite entrar |  |  | pendiente de ejecución |
| PF-014 | Inicio | Cifras acotadas al rol | `funcionario` | Ver `/inicio/` | 3 cifras de atenciones (sin usuarios) |  |  | pendiente de ejecución |
| PF-015 | Inicio | Menú según permisos | `funcionario` | Ver menú lateral | Sin "Usuarios" ni "Delegaciones" |  |  | pendiente de ejecución |
| PF-016 | Delegaciones | Listado solo superadmin | `coordinador` | Acceder a `/delegaciones/` | 403 |  |  | pendiente de ejecución |
| PF-017 | Delegaciones | Crear delegación | `superadmin` | Crear código único y color válido | Aparece en el listado |  |  | pendiente de ejecución |
| PF-018 | Delegaciones | Código duplicado | `superadmin` | Crear con código existente | Error "ya existe" |  |  | pendiente de ejecución |
| PF-019 | Delegaciones | No eliminar con registros | Delegación con usuarios | Intentar eliminar | Bloqueado, sugiere Inactiva |  |  | pendiente de ejecución |
| PF-020 | Roles | Listado solo superadmin | `delegado` | Acceder a `/roles/` | 403 |  |  | pendiente de ejecución |
| PF-021 | Roles | Crear rol con permisos | `superadmin` | Crear rol nuevo | Aparece con sus módulos |  |  | pendiente de ejecución |
| PF-022 | Roles | No eliminar rol de sistema | `superadmin` | Intentar eliminar ROL01 | Bloqueado |  |  | pendiente de ejecución |
| PF-023 | Usuarios | Coordinador ve menor rango | `coordinador` | Ver `/usuarios/` | Solo menor rango de sus delegaciones |  |  | pendiente de ejecución |
| PF-024 | Usuarios | No ver rango igual/superior | `coordinador` | Ver `/usuarios/` | Sin otros coordinadores ni superadmin |  |  | pendiente de ejecución |
| PF-025 | Usuarios | Delegado edita funcionario | `delegado` | Editar funcionario de su delegación | Permite editar |  |  | pendiente de ejecución |
| PF-026 | Usuarios | No asignar rol igual/superior | `coordinador` | Editar e intentar asignar ROL02 | Rol no se ofrece o se rechaza |  |  | pendiente de ejecución |
| PF-027 | Usuarios | No eliminar propio usuario | `superadmin` | Intentar eliminar `superadmin` | Bloqueado |  |  | pendiente de ejecución |
| PF-028 | Ítems | Coordinador crea ítem | `coordinador` | Crear en `/items/nuevo/` | Aparece en el listado |  |  | pendiente de ejecución |
| PF-029 | Ítems | Delegado solo ve/exporta | `delegado` | Ver `/items/` | Sin botones crear/editar/eliminar |  |  | pendiente de ejecución |
| PF-030 | Tipo Atención | Coordinador crea tipo | `coordinador` | Crear tipo activo | Aparece en el listado |  |  | pendiente de ejecución |
| PF-031 | Tipo Atención | Tipo con subtipos no se elimina | `superadmin` | Intentar eliminar | Bloqueado, sugiere Inactivo |  |  | pendiente de ejecución |
| PF-032 | Sub Atención | Solo tipos activos | `coordinador` | Crear sub atención | Selector solo con tipos activos |  |  | pendiente de ejecución |
| PF-033 | Sub Atención | Sub con atenciones no se elimina | `superadmin` | Intentar eliminar | Bloqueado |  |  | pendiente de ejecución |
| PF-034 | Atenciones | Funcionario ingresa atención | `funcionario` | `/atenciones/nuevo/` con datos válidos | Crea con `ATN-XXXX` y SweetAlert |  |  | pendiente de ejecución |
| PF-035 | Atenciones | N° automático y único | — | Crear dos atenciones | Números distintos `ATN-0001` |  |  | pendiente de ejecución |
| PF-036 | Atenciones | Funcionario ve solo lo suyo | `funcionario` | Ver `/atenciones/` | Aviso "solo las atenciones que ingresaste tú" |  |  | pendiente de ejecución |
| PF-037 | Atenciones | No abrir ajena por URL | `funcionario` | Abrir `/atenciones/<pk>/` ajena | 403 |  |  | pendiente de ejecución |
| PF-038 | Atenciones | Búsqueda por N° o solicitante | `coordinador` | Buscar en el listado | Filtra correctamente |  |  | pendiente de ejecución |
| PF-039 | Atenciones | Filtro de estado | `coordinador` | Filtrar "En gestión" | Solo ese estado |  |  | pendiente de ejecución |
| PF-040 | Atenciones | Cambiar delegación activa | `coordinador` | Cambiar selector de cabecera | El listado cambia |  |  | pendiente de ejecución |
| PF-041 | Atenciones | Exportar respeta alcance | `delegado` | Exportar Excel | Solo su delegación |  |  | pendiente de ejecución |
| PF-042 | Atenciones | Delegación fija delegado | `delegado` | Crear atención | Campo fijo "[Asignada por perfil]" |  |  | pendiente de ejecución |
| PF-043 | Atenciones | Descripción mínima | `funcionario` | Descripción corta | Error "al menos 10 caracteres" |  |  | pendiente de ejecución |
| PF-044 | Atenciones | Subtipo depende del tipo | `funcionario` | Cambiar tipo | Subtipo se limpia y recarga |  |  | pendiente de ejecución |
| PF-045 | Seguridad | 403 por URL directa | `funcionario` | Acceder a `/delegaciones/` | 403 sin detalles internos |  |  | pendiente de ejecución |
| PF-046 | Seguridad | 404 inexistente | Sesión iniciada | `/atenciones/999999/` | 404 |  |  | pendiente de ejecución |
| PF-047 | Seguridad | No destructiva por GET | `superadmin` | GET `/delegaciones/<pk>/eliminar/` | 404, no elimina |  |  | pendiente de ejecución |
| PF-048 | Seguridad | CSRF en formularios | — | POST sin token | 403 CSRF |  |  | pendiente de ejecución |
| PF-049 | Seguridad | Cabeceras de seguridad | Sesión iniciada | Inspeccionar respuesta | `X-Frame-Options` y `nosniff` presentes |  |  | pendiente de ejecución |
| PF-050 | Seguridad | Cookie HttpOnly | Sesión iniciada | Inspeccionar cookie | Marca `HttpOnly` |  |  | pendiente de ejecución |
