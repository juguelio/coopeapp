#!/usr/bin/env bash
# Aplica la parte de la ventana de mantenimiento que necesita root.
# Corre EN EL VPS, como root:  sudo ~/odoo-coop/aplicar-mantenimiento.sh
#
# Hace UNA sola cosa: dejar funcionando `location /websocket` en nginx. El
# reboot va aparte y a mano.
#
# Es seguro correrlo dos veces. Y sabe arreglar el caso peor, que es el bloque
# a medias: un /websocket SIN `proxy_http_version 1.1` parece aplicado y no
# funciona — nginx proxea en HTTP/1.0, el header Upgrade se pierde y Odoo
# devuelve 400. Pasó el 2026-08-25 con la primera versión de este script.
#
# No recarga nginx a ciegas: valida con `nginx -t` y, si quedó mal, restaura y
# sale sin recargar. Y al final NO se conforma con "no hay errores en el log":
# hace el handshake de WebSocket y exige un 101.
#
# Para probarlo sin root y sin tocar nginx:
#     cp /etc/nginx/sites-enabled/coopeapp /tmp/prueba.conf
#     CONF=/tmp/prueba.conf DRY_RUN=1 BACKUP=/tmp/prueba.bak ./aplicar-mantenimiento.sh
set -uo pipefail

CONF="${CONF:-/etc/nginx/sites-enabled/coopeapp}"
DRY_RUN="${DRY_RUN:-0}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${BACKUP:-/root/coopeapp-nginx.$STAMP.bak}"
URL="${URL:-https://www.coopeapp.com.ar}"

if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  echo "✗ Esto necesita root. Corrélo así:"
  echo "    sudo $0"
  exit 1
fi

[ -f "$CONF" ] || { echo "✗ No existe $CONF"; exit 1; }

BLOQUE_OK=0
if grep -q "location /websocket" "$CONF"; then
  if grep -A12 "location /websocket" "$CONF" | grep -q "proxy_http_version"; then
    echo "✓ El bloque /websocket ya está y está completo."
    BLOQUE_OK=1
  else
    echo "→ El bloque /websocket existe pero le falta proxy_http_version 1.1."
    echo "  Sin esa línea nginx proxea en HTTP/1.0 y el Upgrade se pierde."
  fi
fi

if [ "$BLOQUE_OK" -eq 0 ]; then
  cp "$CONF" "$BACKUP"
  echo "→ Backup de la config: $BACKUP"

  python3 - "$CONF" <<'PY'
import sys
ruta = sys.argv[1]
s = open(ruta).read()

CABEZA = "    location /websocket {\n        proxy_pass http://odoochat;\n"
LINEA = "        proxy_http_version 1.1;\n"

if "location /websocket" in s:
    # Bloque a medias: solo falta la línea de HTTP/1.1.
    if CABEZA not in s:
        sys.exit("el bloque /websocket no tiene la forma esperada; completalo a mano")
    s = s.replace(CABEZA, CABEZA + LINEA, 1)
    print("→ proxy_http_version 1.1 agregado al bloque existente")
else:
    bloque = '''    location /websocket {
        proxy_pass http://odoochat;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 720s;
    }

'''
    # Se ancla en /longpolling, que es el hermano viejo de esto y está en el
    # server correcto (el de 443).
    ancla = "    location /longpolling {"
    if ancla not in s:
        sys.exit("no encontré 'location /longpolling' — revisá la config a mano")
    if s.count(ancla) != 1:
        sys.exit("hay más de un 'location /longpolling' — revisá la config a mano")
    s = s.replace(ancla, bloque + ancla, 1)
    print("→ Bloque /websocket insertado antes de /longpolling")

open(ruta, "w").write(s)
PY

  if [ $? -ne 0 ]; then
    echo "✗ No se pudo editar la config. Se restaura el backup."
    cp "$BACKUP" "$CONF"
    exit 1
  fi
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  echo "── DRY RUN: no se valida ni se recarga nginx. Así quedó el bloque:"
  sed -n '/location \/websocket/,/^    }/p' "$CONF" | sed 's/^/  /'
  echo
  echo "(tiene que estar proxy_http_version 1.1, y los \$http_upgrade con el"
  echo " signo peso, sin barra invertida adelante)"
  exit 0
fi

if [ "$BLOQUE_OK" -eq 0 ]; then
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
  sleep 2
fi

echo
echo "→ Comprobando que la app siga viva..."
CODIGO="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$URL/app/ingresar")"
echo "  $URL/app/ingresar → http=$CODIGO"
if [ "$CODIGO" != "200" ]; then
  echo "✗ La app NO responde 200. Restaurando la config anterior..."
  [ -f "$BACKUP" ] && cp "$BACKUP" "$CONF" && systemctl reload nginx
  echo "  Config restaurada. Mirá: journalctl -u nginx -n 50"
  exit 1
fi

# Esto es lo que decide. "No hay 400 en el log" NO prueba nada: puede ser que
# no haya tráfico. El handshake tiene que devolver 101 Switching Protocols.
echo "→ Probando el handshake de WebSocket (tiene que dar 101)..."
# El header Origin NO es opcional: Odoo rechaza el handshake sin él con
# "Empty or missing header(s): origin". Sin esta línea el chequeo da 400 con la
# config PERFECTA y manda a arreglar algo que ya funciona — que es la misma
# familia de error que un chequeo que da verde sin haber probado nada.
WS="$(curl -s -o /dev/null -m 15 -w '%{http_code}' \
  -H "Origin: $URL" \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==' \
  "$URL/websocket?version=18.0-7")"
echo "  $URL/websocket → http=$WS"

if [ "$WS" = "101" ]; then
  echo
  echo "✓ El WebSocket conecta. El bus de tiempo real quedó funcionando."
  exit 0
fi

echo
echo "✗ El handshake devolvió $WS en vez de 101. El bus SIGUE sin conectar."
echo "  La config está aplicada pero algo más lo bloquea. Para mirar:"
echo "    grep -A12 'location /websocket' $CONF"
echo "    docker compose -f ~/odoo-coop/docker-compose.yml logs --since 5m odoo | grep websocket"
exit 1
