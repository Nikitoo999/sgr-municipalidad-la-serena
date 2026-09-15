# Sistema de Gestión de Resultados (SGR) — Municipalidad de La Serena
### Prototipo y Mockup Funcional Frontend (Primera Entrega)

Este repositorio contiene el **Mockup Funcional Interactivo** del Sistema de Gestión de Resultados (SGR), desarrollado para la **Municipalidad de La Serena** en el marco de la asignatura **Proyecto Integrado (Analista Programador / Ingeniería en Informática, INACAP)**.

---

## 1. Descripción del Proyecto
El sistema SGR permite planificar, registrar, verificar y monitorear el cumplimiento de metas territoriales, actividades en terreno, compromisos comunitarios y evidencias operativas de las 6 delegaciones municipales de La Serena (Centro, Avenida del Mar, Las Compañías, La Pampa, La Antena - La Florida y Rural).

---

## 2. Tecnologías y Librerías Utilizadas
* **Lenguajes:** HTML5 semántico, CSS3 moderno (Variables CSS, Flexbox, Grid) y JavaScript Vanilla para navegación y validaciones.
* **Tipografías:** [Google Fonts](https://fonts.google.com/) (*Fraunces* para títulos institucionales e *Inter* para interfaz).
* **Paleta Institucional:**
  * Primario Municipal: `#8a2e2e` (Terracota / Ladrillo serenense)
  * Acento Territorial: `#1e5b63` (Azul Océano)
  * Semáforo de Desempeño:
    * Verde (Óptimo $\ge 80\%$): `#3f7d4a`
    * Amarillo (Alerta $60\% - 79.9\%$): `#b9812a`
    * Rojo (Crítico $< 60\%$): `#b23b3b`

---

## 3. Estructura de Navegación del Prototipo
El prototipo cuenta con **40 interfaces interconectadas**:

* `index.html`: Punto de entrada que redirige a la pantalla de autenticación.
* **`vistas/` (20 Módulos de Gestión):**
  1. `01_login.html`: Acceso al sistema con validación de credenciales.
  2. `02_panel_general.html`: Tablero gerencial con vista de las 6 delegaciones.
  3. `03_tubo_kanban.html`: Flujo Kanban de actividades y estados operativos.
  4. `04_delegaciones.html`: Detalle territorial y avance trimestral.
  5. `05_agenda_colectiva.html`: Seguimiento de compromisos vecinales.
  6. `06_reconocimientos.html`: Felicitaciones y reclamos territoriales.
  7. `07_mi_tablero.html`: Vista del funcionario con cálculo de meta esperada diaria.
  8. `08_atencion_social.html`: Registro de atenciones sociales en terreno.
  9. `09_planificacion_territorial.html`: Aprobación y supervisión del Delegado.
  10. `10_validacion_evidencias.html`: Módulo del Verificador técnico.
  11. `11_indicadores.html`: Gráficos de avance y porcentajes de cumplimiento.
  12. `12_cargos_equipos.html`: Distribución jerárquica del personal.
  13. `13_informes_exportacion.html`: Generación de reportes ejecutivos.
  14. `14_usuarios_roles.html`: Administración de funcionarios y permisos.
  15. `15_delegaciones_admin.html`: Mantenedor de delegaciones y períodos.
  16_catalogos.html`: Catálogos maestros (unidades, cargos, tipos).
  17. `17_metas_ponderaciones.html`: Parametrización de ponderaciones (suma 100%).
  18. `18_auditoria.html`: Trazabilidad inmutable de eventos.
  19. `19_alertas.html`: Centro de notificaciones del sistema.
  20. `20_busqueda.html`: Motor de búsqueda global por RUT, código o texto.
* **`formularios/` (13 Formularios Modales):**
  * Alta de actividades, compromisos, funcionarios, delegaciones, atenciones sociales y subida de evidencias.
* **`alertas/` (6 Alertas de Negocio):**
  * Notificaciones de compromisos por vencer, evidencias pendientes, avance bajo umbral, exportación denegada, error en ponderación y usuario duplicado.

---

## 4. Instrucciones de Ejecución
No requiere instalación de servidores pesados ni configuración de bases de datos para esta entrega:
1. Clonar el repositorio:
   ```bash
   git clone <URL_DEL_REPOSITORIO>
   cd sgr_mockup_figma_html
   ```
2. Abrir el archivo `index.html` en cualquier navegador web moderno (Chrome, Edge, Firefox o Safari) haciendo doble clic sobre el archivo.
3. Navegar utilizando el menú lateral y las acciones de los botones.

---

## 5. Trazabilidad con la Entrega
* **Casos de Uso:** Cubre el 100% de los casos de uso específicos (CU-01 al CU-12).
* **Modelo de Datos:** Cada vista refleja exactamente los atributos de las 19 tablas del modelo entidad-relación (MySQL).
* **Rúbrica de Evaluación:** Cumple a cabalidad con la Sección 7.2 (Navegación, fluidez, validaciones, responsive y código versionado).
