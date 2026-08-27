#!/usr/bin/env bash
# Configura el AUTO-DEPLOY por GitHub Actions (una sola vez, desde la Mac).
#
# Hace todo solo:
#   1. crea una llave SSH DEDICADA para CI (separada de la tuya personal)
#   2. la instala en el VPS (usa tu acceso passwordless ya configurado)
#   3. carga los secrets en GitHub con gh (private key, host, user, known_hosts)
#
# Requisitos previos:
#   - scripts/setup-ssh.sh corrido (alias coopeapp-vps funcionando)
#   - gh (GitHub CLI) autenticado: gh auth status
#
# Después de esto: cada push a main que toque addons/ deploya solo.
set -euo pipefail

VPS_USER="odoo-admin"
VPS_HOST="178.105.15.189"
CI_KEY="$HOME/.ssh/coopeapp_ci"

command -v gh >/dev/null || {
  echo "✗ Falta GitHub CLI (gh). Instalalo (brew install gh) y corré 'gh auth login'."
  exit 1; }
gh auth status >/dev/null 2>&1 || { echo "✗ gh no está autenticado. Corré: gh auth login"; exit 1; }

# 1. llave dedicada de CI ─────────────────────────────────────────────
if [ ! -f "$CI_KEY" ]; then
  echo "→ Generando llave dedicada de CI..."
  ssh-keygen -t ed25519 -N "" -C "coopeapp-ci-deploy" -f "$CI_KEY"
fi

# 2. instalar la pubkey en el VPS, ACOTADA ────────────────────────────
# Ojo: la versión original de este script instalaba la llave pelada, sin
# `restrict` ni `command=`. Eso le daba una shell completa como odoo-admin, que
# por estar en el grupo docker es root: la llave que vive en los secrets de
# GitHub era una llave de root. Ver docs/seguridad-vps.md.
echo "→ Instalando la llave de CI en el VPS (acotada)..."
PUB="$(cat "$CI_KEY.pub")"
FORZADO="/home/$VPS_USER/odoo-coop/ci-forced-command.sh"
scp -q "$(dirname "$0")/vps/ci-forced-command.sh" \
       "$(dirname "$0")/vps/deploy-modulos.sh" coopeapp-vps:~/odoo-coop/
ssh coopeapp-vps "
  set -e
  chmod 700 ~/odoo-coop/ci-forced-command.sh ~/odoo-coop/deploy-modulos.sh
  install -d -m 700 ~/.ssh
  touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
  cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak.\$(date +%Y%m%d%H%M%S)
  grep -v 'coopeapp-ci-deploy' ~/.ssh/authorized_keys > /tmp/ak || true
  echo 'restrict,command=\"$FORZADO\" $PUB' >> /tmp/ak
  install -m 600 /tmp/ak ~/.ssh/authorized_keys && rm -f /tmp/ak
"

# 3. cargar secrets en GitHub ─────────────────────────────────────────
echo "→ Cargando secrets en GitHub..."
gh secret set VPS_SSH_PRIVATE_KEY < "$CI_KEY"
printf '%s' "$VPS_HOST" | gh secret set VPS_HOST
printf '%s' "$VPS_USER" | gh secret set VPS_USER
ssh-keyscan -H "$VPS_HOST" 2>/dev/null | gh secret set VPS_KNOWN_HOSTS

echo
echo "✓ Auto-deploy configurado."
echo "  Probalo:  git commit --allow-empty -m 'ci: probar deploy' && git push"
echo "  y mirá la pestaña Actions del repo (o: gh run watch)."
echo
echo "  Verificá que quedó acotada:  ./scripts/verificar-llave-ci.sh"
echo
echo "  Para revocar el acceso de CI en el futuro: borrá la línea 'coopeapp-ci-deploy'"
echo "  de ~/.ssh/authorized_keys en el VPS."
