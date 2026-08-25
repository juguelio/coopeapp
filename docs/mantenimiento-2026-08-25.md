# Ventana de mantenimiento — 2026-08-25

Estado de la tarea 3. Lo que **no** necesita `sudo` ya está hecho y verificado.
Lo que sigue lo tenés que correr vos: el usuario `odoo-admin` puede usar docker
pero `sudo` pide contraseña, así que nginx y el reboot no los puedo tocar.

Backup del día verificado antes de tocar nada: `db_coop_piloto_2026-08-25_030001.dump`,
5.341.193 bytes, y `pg_restore -l` lista 442 tablas con datos — o sea que es
legible, no un archivo vacío.

---

## Hecho y verificado

| Ítem | Estado |
|---|---|
| Cerrar 8069/8072 | ✅ **ya estaba** — bindeados a `127.0.0.1`, verificado desde afuera con curl: dan timeout, mientras 443 y 80 responden |
| `list_db = False` | ✅ aplicado — el endpoint `db.list` ahora devuelve `AccessDenied`, verificado por comportamiento |
| Rotar `admin_passwd` | ✅ rotada a 28 caracteres. **La contraseña te la paso aparte: va al gestor, no al repo ni a este archivo** |
| Aislamiento de memoria en test | ✅ techo de 1 GB en el contenedor de test (`e1eadd7`), verificado leyendo el límite efectivo del contenedor |

Rollback de los configs: `/tmp/odoo.conf.antes-mantenimiento-2026-08-25` y
`/tmp/docker-compose.yml.antes-mantenimiento-2026-08-25` en el VPS.

---

## 1. nginx: la ruta `/websocket` (necesita sudo)

El bus de tiempo real de Odoo 18 usa `/websocket`. La config tiene
`location /longpolling`, que es el nombre de Odoo 15. En el log de producción
se ve en crudo:

```
"GET /websocket?version=18.0-7 HTTP/1.0" 400
```

No afecta `/app` — sí las notificaciones del backoffice.

Agregá este bloque en `/etc/nginx/sites-enabled/coopeapp`, dentro del `server`
que escucha en 443, al lado del `location /longpolling` que ya está:

```nginx
    location /websocket {
        proxy_pass http://odoochat;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 720s;
    }
```

El `upstream odoochat` ya existe y apunta al 8072, así que no hay que tocarlo.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Cómo saber si funcionó** (no alcanza con que recargue):

```bash
# antes daba 400; tiene que dejar de darlo
docker compose -f ~/odoo-coop/docker-compose.yml logs --since 2m odoo | grep websocket
```

Y en el navegador, abrir el backoffice y mirar que no haya errores de
conexión del bus en la consola.

---

## 2. Bloquear el gestor de bases desde nginx (opcional, recomendado)

`list_db = False` ya impide **enumerar** las bases, pero `/web/database/manager`
sigue respondiendo y pidiendo la Master Password. Si nadie la usa desde
internet, conviene no exponerla:

```nginx
    location ~* ^/web/database/(manager|selector|create|drop|duplicate|restore|backup) {
        return 404;
    }
```

⚠️ Si alguna vez hace falta usarla, se hace por un túnel ssh contra el 8069
local, no reabriendo esto.

---

## 3. Reboot (necesita sudo)

`/var/run/reboot-required` está presente y el uptime es de **18 semanas**.

```bash
sudo reboot
```

Los dos contenedores tienen `restart: unless-stopped`, así que levantan solos.

**Verificación después del reboot** — esto es lo que importa, porque los
backups cubren los datos pero no que el server vuelva:

```bash
uptime                                  # tiene que ser de minutos
docker ps                               # los dos contenedores Up
curl -s -o /dev/null -w '%{http_code}\n' https://www.coopeapp.com.ar/app/ingresar
```

Y un login real de socio, que es la prueba de que Odoo levantó de verdad y no
solo el contenedor.

---

## 4. Lo que queda anotado, sin hacer

- **No hay swap** (`Swap: 0`). Con 3819 MB totales y sin swap, el kernel no
  tiene ningún colchón: cuando la memoria se acaba, elige una víctima y la
  mata. Un archivo de swap de 2 GB haría que el 24/08 no volviera a pasar
  aunque el techo del test falle. Necesita sudo.
- **Postgres compartido.** El techo del contenedor de test es una mitigación,
  no aislamiento. El aislamiento de verdad es un Postgres aparte para pruebas.
  Con 3819 MB y sin swap, hoy no entra cómodo: primero el swap.
