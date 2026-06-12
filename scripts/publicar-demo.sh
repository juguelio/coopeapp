#!/usr/bin/env bash
# Publica el mockup de la app de socios en https://coopeapp.com.ar/demo
# Uso: ./scripts/publicar-demo.sh
set -euo pipefail

VPS="odoo-admin@178.105.15.189"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MOCKUP="$REPO/docs/mockup-ui-socios.html"

[ -f "$MOCKUP" ] || { echo "No existe $MOCKUP"; exit 1; }

echo "→ Subiendo mockup al VPS..."
scp "$MOCKUP" "$VPS:/tmp/demo-index.html"

echo "→ Instalando en /var/www/coopeapp-demo..."
ssh "$VPS" "sudo mkdir -p /var/www/coopeapp-demo && sudo mv /tmp/demo-index.html /var/www/coopeapp-demo/index.html && sudo chown -R www-data:www-data /var/www/coopeapp-demo"

echo "→ Verificando nginx..."
if ssh "$VPS" "grep -q coopeapp-demo /etc/nginx/sites-enabled/* 2>/dev/null"; then
  ssh "$VPS" "sudo nginx -t && sudo systemctl reload nginx"
  echo "✓ Demo publicada: https://coopeapp.com.ar/demo"
else
  cat << 'NGINX'
⚠️ Falta el bloque en nginx (una sola vez). En el VPS, dentro del server {}
de coopeapp.com.ar (/etc/nginx/sites-enabled/...), agregar:

    location /demo {
        alias /var/www/coopeapp-demo;
        index index.html;
    }

y después:  sudo nginx -t && sudo systemctl reload nginx
NGINX
fi
