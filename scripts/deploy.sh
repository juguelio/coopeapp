#!/usr/bin/env bash
# Deploy de un módulo al VPS. Uso: ./scripts/deploy.sh coop_construction
set -euo pipefail

MODULO="${1:?Uso: ./scripts/deploy.sh NOMBRE_MODULO}"
VPS="odoo-admin@178.105.15.189"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

[ -d "$REPO/addons/$MODULO" ] || { echo "No existe addons/$MODULO"; exit 1; }

echo "→ Subiendo $MODULO al VPS..."
scp -r "$REPO/addons/$MODULO/" "$VPS:~/odoo-coop/addons/"

echo "→ Actualizando módulo en Odoo..."
ssh "$VPS" "cd ~/odoo-coop && docker compose run --rm odoo odoo -u $MODULO -d coop_piloto --stop-after-init && docker compose restart odoo"

echo "✓ Deploy de $MODULO completo. Logs: ssh $VPS 'cd ~/odoo-coop && docker compose logs -f odoo'"
