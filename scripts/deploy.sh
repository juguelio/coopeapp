#!/usr/bin/env bash
# Deploy de uno o varios módulos al VPS.
# Uso: ./scripts/deploy.sh coop_construction
#      ./scripts/deploy.sh coop_construction,coop_portal
# Con la llave SSH configurada (ver scripts/setup-ssh.sh) no pide password.
set -euo pipefail

MODULOS="${1:?Uso: ./scripts/deploy.sh MODULO[,MODULO2,...]}"
VPS="odoo-admin@178.105.15.189"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DB="coop_piloto"

# reusar una sola conexión SSH (un solo prompt de password si no hay llave)
CTL="/tmp/coopeapp-ssh-%r@%h:%p"
SSH_OPTS=(-o "ControlMaster=auto" -o "ControlPath=$CTL" -o "ControlPersist=120")
trap 'ssh "${SSH_OPTS[@]}" -O exit "$VPS" 2>/dev/null || true' EXIT

IFS=',' read -ra LISTA <<< "$MODULOS"
for m in "${LISTA[@]}"; do
  [ -d "$REPO/addons/$m" ] || { echo "✗ No existe addons/$m"; exit 1; }
  # no subir __pycache__ (se generan en el server con la versión correcta)
  find "$REPO/addons/$m" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  echo "→ Subiendo $m..."
  scp "${SSH_OPTS[@]}" -rq "$REPO/addons/$m" "$VPS:~/odoo-coop/addons/"
done

echo "→ Limpiando caché y actualizando ($MODULOS)..."
ssh "${SSH_OPTS[@]}" "$VPS" "
  set -e
  cd ~/odoo-coop
  for m in $(echo "$MODULOS" | tr ',' ' '); do
    find addons/\$m -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  done
  docker compose run --rm odoo odoo -u $MODULOS -d $DB --stop-after-init
  docker compose restart odoo
"
echo "✓ Deploy de $MODULOS completo → https://www.coopeapp.com.ar/app"
