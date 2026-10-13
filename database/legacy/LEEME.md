# Diseño SQL inicial (legado)

`sgr_municipalidad_laserena_mysql.sql` es el diseño inicial de Análisis y
Diseño. **Ya no refleja el sistema**: el esquema vigente lo definen los
modelos Django (apps `sgr_core`, `operaciones`, `portal`) y sus migraciones.

No se usa para crear ni migrar la base de datos. Se conserva solo como
referencia histórica.

Nota: `sgr_laserena_mariadb_schema.sql` (en `database/`) tampoco se regenera
desde este proyecto: se obtiene con `mysqldump` sobre una base MariaDB real
(lo hace el integrante encargado, no este flujo).