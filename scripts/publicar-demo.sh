#!/usr/bin/env bash
# Publica el mockup de la app de socios en https://coopeapp.com.ar/demo
# Uso: ./scripts/publicar-demo.sh   (pide la password de SSH y la de sudo)
set -euo pipefail

VPS="odoo-admin@178.105.15.189"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MOCKUP="$REPO/docs/mockup-ui-socios.html"

[ -f "$MOCKUP" ] || { echo "No existe $MOCKUP"; exit 1; }

echo "→ Subiendo mockup..."
scp "$MOCKUP" "$VPS:/tmp/demo-index.html"

echo "→ Instalando y configurando nginx (pide password de sudo)..."
ssh -t "$VPS" '
set -e
# limpiar el archivo basura de un intento anterior, si quedó
sudo rm -f "/etc/nginx/sites-enabled/EL_ARCHIVO_QUE_TE_DIO"

sudo mkdir -p /var/www/coopeapp-demo
sudo mv /tmp/demo-index.html /var/www/coopeapp-demo/index.html
sudo chown -R www-data:www-data /var/www/coopeapp-demo

# buscar la config (-R sigue symlinks, sites-enabled suele ser un link)
F=$(sudo grep -Rl "coopeapp" /etc/nginx/sites-enabled/ /etc/nginx/sites-available/ /etc/nginx/conf.d/ 2>/dev/null | head -1)
if [ -z "$F" ]; then
  F=$(sudo grep -Rl "listen 443" /etc/nginx/sites-enabled/ /etc/nginx/sites-available/ /etc/nginx/conf.d/ 2>/dev/null | head -1)
fi
if [ -z "$F" ]; then
  echo "================================================"
  echo "No encontre la config. Esto es lo que hay en /etc/nginx:"
  sudo ls -la /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null
  echo "--- servers definidos: ---"
  sudo nginx -T 2>/dev/null | grep -E "server_name|listen|# configuration file" | head -30
  echo "================================================"
  exit 1
fi
echo "Config nginx: $F"
# backup FUERA de sites-enabled (nginx carga todo lo que hay ahí)
sudo cp "$F" "/var/backups/coopeapp-nginx-$(date +%Y%m%d-%H%M%S).bak"

sudo python3 - "$F" <<PY
import sys
f = sys.argv[1]
s = open(f).read()
if "location /demo/" in s:
    print("nginx: el bloque /demo ya estaba")
else:
    i = s.find("listen 443")
    if i == -1:
        i = s.find("listen [::]:443")
    if i == -1:
        i = s.find("listen 80")
    if i == -1:
        sys.exit("No encontre ningun server (443/80) en " + f)
    j = s.find(";", i) + 1
    b = "\n    location /demo/ { alias /var/www/coopeapp-demo/; index index.html; }\n    location = /demo { return 301 /demo/; }\n"
    open(f, "w").write(s[:j] + b + s[j:])
    print("nginx: bloque /demo agregado")
PY

# limpiar backups viejos que hayan quedado dentro de sites-enabled
sudo find /etc/nginx/sites-enabled/ -name "*.bak*" -exec mv {} /tmp/ \; 2>/dev/null || true

sudo nginx -t
sudo systemctl reload nginx
echo "LISTO → https://www.coopeapp.com.ar/demo"
'
