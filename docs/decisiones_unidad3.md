# Decisiones y supuestos de la Unidad 3

La Guía del proyecto pide que las ambigüedades "no se resuelvan silenciosamente:
se documentan como supuestos o consultas al docente". Este documento registra cómo
se interpretó cada requerimiento de la Unidad 3 (correo "Nuevo Requerimiento",
base de organizaciones comunitarias, descriptor de funciones, formato de tubo y
preview de implementación) y qué queda por confirmar con la Municipalidad.

## Nuevo requerimiento de la matriz (correo de coordinación)

| Punto | Regla | Implementación | Por confirmar |
|---|---|---|---|
| 1 | No cuentan las actividades y solicitudes donde el usuario es el delegado | Si el RUT del solicitante es el de un funcionario, se pregunta si acude **como civil** o si es **gestión interna**; la gestión interna no suma. Se mantiene además la regla anterior: lo que ingresa el rol Delegado no suma. | ¿La exclusión aplica solo al delegado o a cualquier funcionario como solicitante? Hoy aplica a cualquier funcionario que no acuda como civil. |
| 2 | Sin nombre y teléfono del usuario no hay puntuación | Atenciones: nombre y teléfono son obligatorios. Actividades: se agregan nombre y teléfono del contacto; si el ítem es "de cara al usuario" (`requires_contact`) y faltan, la actividad no suma. Tubo: sin teléfono la solicitud realizada no suma. Ítems internos (informes, inventarios, operativos, reunión de equipo) no exigen contacto. | Lista de ítems internos. |
| 3 | Máximo 7 ingresos diarios | Tope al ingresar atenciones y tope de 7 registros contados por día en la matriz (actividades y atenciones juntas). | — |
| 4 | Desde el martes no se ingresa la semana anterior | Cierre automático de la semana el martes siguiente (atenciones, actividades y tubo). El cierre manual semanal sigue disponible. | — |
| 5 | Las gestiones preparatorias no dan punto | Sub atención con la marca "Suma puntaje"; las preparatorias se desmarcan. | Qué sub atenciones son preparatorias. |
| 6 | No ingresar solo para generar puntaje | Lo que un funcionario registra para sí mismo no suma; alertas de ingresos sobre el tope y de ausencia de registros. | — |
| 7 | Sobre el 120 % un ítem no sube más | Tope de 120 % por ítem (`SGR_TOPE_CUMPLIMIENTO`). La Guía académica propone 150 %: prevalece el valor del cliente. | — |
| 8 | Felicitaciones con respaldo formal, informadas por el delegado | Solo el delegado o un rol superior registra felicitaciones y reclamos; sin respaldo no suman. | — |
| 9 | Días libres ingresados por el delegado en el semáforo | Registro de días libres en Cumplimiento (delegado o superior); ajusta la meta. | — |
| 10 | Puntajes de equipo | Resumen de la delegación: puntaje del equipo, semáforo e ítems a reforzar. | — |

## Funcionario que retira material como civil

- El sistema **detecta** el RUT de un funcionario al ingresar la atención y lo informa (nombre y delegación).
- Nunca bloquea: se elige "Atender como civil" (sigue el flujo normal, por ejemplo "Informe aporte material") o "Gestión interna" (no suma).
- No se duplica a la persona: el registro de vecino queda vinculado al funcionario (`Neighbor.employee`) y la atención guarda al funcionario solicitante (`requester_employee`).
- Si el funcionario registra su propia solicitud, queda registrada pero no suma puntaje.

## Matriz y validación

- **Las atenciones suman a la matriz.** Cada atención lleva el ítem de la matriz, elegido entre los ítems del cargo del responsable en el período vigente (RF-003). La sub atención propone un ítem sugerido.
- **Solo lo validado suma** (RN-009). Una atención necesita evidencia y validación aprobada por el delegado o un rol superior, nunca por quien la registró. Las evidencias de la agenda se aprueban, se rechazan o se pide corrección, siempre con observación. Si se editan datos que puntúan, la validación vuelve a "Pendiente".
- **Metas y ponderadores.** Son por cargo y período, y deben sumar 100 % (RN-001). Se acepta una excepción formal con motivo, que queda en la auditoría: el Excel municipal trae cargos que suman 85 %.

## Períodos y cierre de trimestre

- Los períodos son globales: crearlos, cerrarlos o reabrirlos corresponde al superadministrador. Coordinadores y delegados los consultan.
- **Al cerrar un trimestre:**
  - Las solicitudes del tubo y las atenciones abiertas pasan al siguiente marcadas como PRIORITARIAS.
  - Se genera un aviso por delegación.
  - Las solicitudes traspasadas cuentan en el % del tubo del nuevo trimestre.
- Un período cerrado no se modifica (RN-013). La reapertura exige motivo y queda auditada.
- **Período vigente:** el que contiene la fecha de hoy. Todas las pantallas usan la misma regla.

## Organigramas

- **Organigrama de funcionarios** (Usuarios): funcionarios por delegación y cargo. Se corrigió que aparecía vacío.
- **Organigrama de la organización** (preview, `/organizaciones/organigrama/`): directiva de cada junta de vecinos u organización, con cargos base Presidente/a, Secretario/a y Tesorero/a y cargos creados. Sus integrantes se usan en el ingreso "Directivo de organización".
  - Los cargos se ordenan en tres niveles: 1 Presidencia (Presidente/a, Vicepresidente/a), 2 Directiva (Secretario/a, Tesorero/a) y 3 Delegaciones, vocalías y otros cargos. El orden ubica el cargo dentro de su nivel.
  - Cada cargo activo aparece aunque esté vacante, para asignarlo desde el mismo nodo. Una organización tiene un integrante por cargo.
  - El catálogo de cargos es común a todas las organizaciones. Los cargos base no se renombran ni se eliminan. Un cargo creado se elimina solo si nadie lo ocupa, y solo el superadministrador elimina, como en el resto del sistema.
  - No es un organigrama de Recursos Humanos: los funcionarios municipales están en el organigrama de Usuarios.

## Datos personales

- La base de organizaciones (personas jurídicas) se carga localmente desde `data/`, que no se versiona.
- En la demo, los directivos y vecinos son ficticios, como exige la Guía.
