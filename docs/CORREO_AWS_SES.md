# Correo de recuperación de contraseña con AWS SES

El sistema ya trae el flujo completo de recuperación (`/password-reset/`, enlace en la
pantalla de login). Falta solo conectar el envío a **Amazon SES** usando variables en `.env`.
Sin esas variables, el correo se imprime en la consola del servidor (modo desarrollo).

## 1. Qué se hace en AWS (consola web)

1. Entra a la consola de AWS → **Amazon SES**. Elige una región (ej. `us-east-1`) y
   **usa siempre la misma** en todo el proceso.
2. **Verified identities → Create identity**:
   * *Email address*: ingresa el correo desde el que enviará el sistema (ej. el tuyo o
     uno del equipo) y abre el correo de AWS para hacer clic en el enlace de verificación.
   * *(Opcional, recomendado)* *Domain*: si tienen un dominio propio, verifícalo (AWS
     entrega registros DNS/DKIM que se agregan en el proveedor del dominio).
3. **SMTP settings → Create SMTP credentials**. AWS crea un usuario IAM y muestra el
   **usuario SMTP** y la **contraseña SMTP**. **Se ven una sola vez: cópialas.**
   (No son la clave de acceso normal de AWS ni la contraseña de la cuenta.)
4. **Modo sandbox**: toda cuenta nueva parte en *sandbox*. En sandbox SES **solo envía a
   correos verificados** (repite el paso 2 para cada correo de prueba que reciba mensajes),
   con un tope diario bajo. Para enviar a cualquier destinatario hay que pedir
   **Request production access** en la consola de SES (AWS tarda ~1 día).
   Para la evidencia del trabajo basta con el sandbox.

## 2. Qué se hace en el proyecto (`.env`)

Agrega (o descomenta) estas líneas, con TUS valores:

```
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<usuario SMTP de SES>
EMAIL_HOST_PASSWORD=<contraseña SMTP de SES>
DEFAULT_FROM_EMAIL=SGR La Serena <correo-verificado@ejemplo.cl>
```

* El host debe coincidir con la región elegida (`email-smtp.<region>.amazonaws.com`).
* `DEFAULT_FROM_EMAIL` debe ser un correo o dominio **verificado** en SES.
* El archivo `.env` está en `.gitignore`: **nunca** subas estas credenciales a git.
* Reinicia la app tras cambiar el `.env` (`sudo systemctl restart sgr` en EC2).
* Se usa el puerto **587** (el 25 está limitado por AWS en EC2).

## 3. Cómo probarlo

1. Ponle un correo real (verificado en SES) a un usuario, desde el admin
   (Usuarios → editar → *Correo electrónico*) o al cargar los datos de prueba:

   ```bash
   python manage.py seed_demo --demo-email tu_correo_verificado@ejemplo.cl
   ```
   (esto asigna el correo al usuario `jefatura_centro`).
2. Entra a `/login/` → **¿Olvidó su contraseña?** → escribe ese correo.
3. Debe llegar un mensaje "Recuperación de contraseña SGR La Serena" con un enlace
   (vence en 1 hora). Revisa también *spam*.
4. Abre el enlace, define una contraseña nueva e inicia sesión.

## 4. Si no llega

| Síntoma | Causa probable |
|---|---|
| La página dice "enviado" pero no llega nada | El correo destino no está verificado (sandbox) o el usuario no tiene ese correo guardado. Django no avisa si el correo no existe (a propósito, por seguridad). |
| Error `SMTPAuthenticationError` en los logs | Usuario/contraseña SMTP mal copiados, o se usó la clave IAM normal en vez de las credenciales SMTP. |
| `MessageRejected: Email address is not verified` | `DEFAULT_FROM_EMAIL` no está verificado, o la región del host no coincide con donde se verificó. |
| Timeout / se queda pegado | Puerto 25 en vez de 587, o el Security Group bloquea salidas (por defecto permite todas). |

Logs en EC2: `sudo journalctl -u sgr -n 100 --no-pager`.
