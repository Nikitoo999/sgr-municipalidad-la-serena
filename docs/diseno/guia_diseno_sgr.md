# Guía de diseño del SGR (referencia para implementar)

Fuente visual: `docs/diseno/sgr_mockup_referencia.html` (abrir en el navegador y cambiar "Ver como" para ver cada rol). Si esta guía y el mockup difieren, manda el mockup. Los permisos reales salen siempre de `portal/access.py`, nunca del mockup.

## 1. Colores
| Uso | Valor |
|---|---|
| Rojo institucional (barra superior, riel, botón primario) | #920000 |
| Rojo del panel de Mantenedores (un poco más claro) | #a82020 |
| Fondo de página | #f6f4f4 |
| Texto / texto secundario / borde | #1f1a1a / #6b6262 / #e6dfdf |
| Encabezado de tabla / fila al pasar el mouse | #eceff3 / #fdf3f3 |

Colores de delegación (tomados de las capturas; usar los que ya define el sistema si difieren):
DEL01 Centro #4f6dbd · DEL02 Avenida del Mar #1f6fb5 · DEL03 La Antena-La Florida #2a7d34 · DEL04 Las Compañías #7b2fa0 · DEL05 La Pampa #c2410c · DEL06 Rural #0b7a5a · "Todas las delegaciones" #334155.

Estados: Ingresada (fondo #dbeafe, texto #1e40af) · En gestión (#fef3c7, #92400e) · Resuelta y Activo (#dcfce7, #166534). Semáforo de cumplimiento: verde desde 80 %, ámbar desde 50 %, rojo bajo 50 %.

## 2. Estructura de la pantalla
- Barra superior de ancho completo, 56 px, roja. Izquierda: escudo, "LA SERENA / ILUSTRE MUNICIPALIDAD" y SGR. Derecha: campana, selector de delegación (solo si el rol tiene varias) y perfil.
- Bajo la barra, una línea de 3 px con degradé del color de la delegación activa, intensa a la derecha y transparente a la izquierda.
- Debajo: riel (60 px; 220 px expandido), panel de Mantenedores (56 px solo íconos; 190 px expandido) y contenido (relleno 24 px).
- Riel y panel se expanden al pasar el mouse y **empujan el contenido**, nunca lo tapan. Animación de 0,15 s. "Fijar menú" y "Contraer panel" dejan el estado fijo.
- El ícono Mantenedores del riel abre o cierra el panel sin cambiar de página. Otros íconos del riel cierran el panel.

## 3. Rectángulos de la barra superior
Selector de delegación y perfil: borde de 2 px del color de la delegación, fondo de ese mismo color mezclado al 10 % con blanco, texto del color de la delegación. El perfil muestra nombre y cargo, y su menú incluye Configuración de perfil y Salir (por POST).

## 4. Componentes
- Cuadros de delegación (por ejemplo "DEL01 · Centro"): borde del color de la delegación, fondo al 10 %, texto oscuro. Sin cuadradito de color.
- Botón primario: rojo, 40 px de alto, radio 8. Secundario: borde rojo, fondo blanco.
- Botones de acción por módulo: "+ Nueva delegación", "+ Nuevo rol", "+ Nuevo usuario", "+ Nuevo ítem", "+ Nuevo tipo de atención", "+ Nueva sub atención". En Atenciones: "+ Registrar atención".
- Listados: tarjeta de búsqueda (lupa, ícono "Limpiar filtros" con etiqueta, "Exportar a Excel"); botones de estado con contador (Todos, y los estados del módulo); grilla de filtros del módulo; etiquetas de filtros activos con ×; tabla; pie con "Mostrando X a Y de Z", filas por página (5, 10, 20) y paginación.
- Filtros por módulo: Usuarios (Rol, Delegación), Sub atenciones (Tipo asociado), Atenciones (Tipo, Sub atención según el tipo, Delegación, Responsable, Desde, Hasta).
- Tabla: textos largos en 2 líneas con puntos suspensivos y descripción completa al pasar el mouse. La columna Acciones nunca queda oculta.
- Acciones: ver (azul #1e40af), editar (#92400e), eliminar (#b91c1c, **solo superadministrador**).
- Ventanas emergentes: foco al primer campo, Esc o clic fuera cierran, el Tab no sale de la ventana, errores junto al campo, avisos de 2,5 s.
- Exportar a Excel: descarga un .csv (UTF-8) con exactamente los registros filtrados.
- Ficha de atención: datos del solicitante, bitácora con fecha, hora y responsable, estado de la evidencia y cambio de estado hacia adelante (Ingresada, En gestión, Resuelta) con nota.

## 5. Reglas por rol (ejemplo del mockup; la fuente real es access.py)
| Rol | Módulos | Selector de delegación | Otros |
|---|---|---|---|
| Superadministrador | 11 | "Todas" y las 6 | Único que elimina |
| Coordinador | 9 | Solo sus delegaciones autorizadas | |
| Delegado municipal | 4 | No, delegación fija | |
| Funcionario | 2 | No, delegación fija | Solo sus registros; sin ícono Mantenedores |

## 6. Accesibilidad
Contraste mínimo AA, foco visible, nombre accesible en todos los botones de ícono, uso completo con teclado.

## 7. Pendiente de definir
Escudo y tipografía oficiales de la Municipalidad (el mockup usa un cuadro "LS" y la letra del sistema).
