#!/usr/bin/env bash
# Aplica la parte de la ventana de mantenimiento que necesita root.
# Corre EN EL VPS, como root:  sudo ~/odoo-coop/aplicar-mantenimiento.sh
#
# Hace UNA sola cosa: agregar `location /websocket` a nginx. El reboot va
# aparte y a mano, para que vos decidas cuándo.
#
# Es seguro de correr dos veces: si el bloque ya está, no hace nada.
#
# Y no recarga nginx a ciegas: valida la config con `nginx -t` y, si quedó
# mal, restaura el backup y sale sin tocar nada. Una config rota recargada
# tira el sitio abajo, y ese es el error que este script existe para no
# cometer.
set -uo pipefail

# CONF y DRY_RUN se pueden sobreescribir para PROBAR el script sin root y sin
# tocar el nginx de verdad:
#     cp /etc/nginx/sites-enabled/coopeapp /tmp/prueba.conf
#     CONF=/tmp/prueba.conf DRY_RUN=1 ./aplicar-mantenimiento.sh
# Así se verifica que el bloque queda bien escrito —con los $http_upgrade
# literales, no expandidos por el shell— antes de correrlo en serio.
CONF="${CONF:-/etc/nginx/sites-enabled/coopeapp}"
DRY_RUN="${DRY_RUN:-0}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${BACKUP:-/root/coopeapp-nginx.$STAMP.bak}"

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  echo "✗ Esto necesita root. Corrélo así:"
  echo "    sudo $0"
  exit 1
fi

[ -f "$CONF" ] || { echo "✗ No existe $CONF"; exit 1; }

if grep -q "location /websocket" "$CONF"; then
  echo "✓ El bloque /websocket ya estaba. No hay nada que hacer."
  echo "  (si igual querés recargar: nginx -t && systemctl reload nginx)"
  exit 0
fi

cp "$CONF" "$BACKUP"
echo "→ Backup de la config: $BACKUP"

python3 - "$CONF" <<'PY'
import sys, re
ruta = sys.argv[1]
s = open(ruta).read()

bloque = '''    location /websocket {
        proxy_pass http://odoochat;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 720s;
    }

'''

# Se ancla en el `location /longpolling`, que es el hermano viejo de esto y
# está en el server correcto (el de 443). Anclar en `location /` sería
# ambiguo si algún día hay más de un server block.
ancla = "    location /longpolling {"
if ancla not in s:
    sys.exit("no encontré 'location /longpolling' — revisá la config a mano")
if s.count(ancla) != 1:
    sys.exit("hay más de un 'location /longpolling' — revisá la config a mano")

s = s.replace(ancla, bloque + ancla, 1)
open(ruta, "w").write(s)
print("→ Bloque /websocket insertado antes de /longpolling")
PY
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "✗ No se pudo editar la config. Se restaura el backup."
  cp "$BACKUP" "$CONF"
  exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "── DRY RUN: no se valida ni se recarga nginx. Así quedó el bloque:"
  sed -n '/location \/websocket/,/^    }/p' "$CONF" | sed 's/^/  /'
  echo
  echo "(los \$http_upgrade y \$host tienen que verse con el signo peso,"
  echo " sin barra invertida adelante)"
  exit 0
fi

echo "→ Validando la config (nginx -t)..."
if ! nginx -t; then
  echo
  echo "✗ La config quedó inválida. Se restaura el backup y NO se recarga."
  cp "$BACKUP" "$CONF"
  nginx -t && echo "  (config original restaurada y válida)"
  exit 1
fi

echo "→ Recargando nginx..."
systemctl reload nginx || { echo "✗ Falló el reload."; cp "$BACKUP" "$CONF"; exit 1; }

echo
echo "✓ nginx recargado con /websocket."
echo
echo "→ Comprobando que la app siga viva..."
CODIGO="$(curl -s -o /dev/null -w '%{http_code}' https://www.coopeapp.com.ar/app/ingresar)"
echo "  https://www.coopeapp.com.ar/app/ingresar → http=$CODIGO"
if [ "$CODIGO" != "200" ]; then
  echo "✗ La app NO responde 200. Restaurando la config anterior..."
  cp "$BACKUP" "$CONF"
  systemctl reload nginx
  echo "  Config restaurada. Mirá: journalctl -u nginx -n 50"
  exit 1
fi

echo
echo "Ahora, para confirmar que el websocket dejó de dar 400:"
echo "    su - odoo-admin -c 'cd ~/odoo-coop && docker compose logs --since 5m odoo | grep websocket'"
echo
echo "Antes daba:  \"GET /websocket?version=18.0-7 HTTP/1.0\" 400"
echo "Tiene que dejar de aparecer ese 400 con los accesos nuevos."
