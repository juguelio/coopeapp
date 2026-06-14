#!/usr/bin/env bash
# Configura acceso SSH SIN password al VPS (una sola vez).
# Después de esto, ./scripts/deploy.sh no vuelve a pedir contraseña.
set -euo pipefail
VPS="odoo-admin@178.105.15.189"

# 1. crear una llave si no existe
if [ ! -f ~/.ssh/id_ed25519 ]; then
  ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
fi

# 2. copiarla al VPS (te pide la password UNA última vez)
ssh-copy-id -i ~/.ssh/id_ed25519.pub "$VPS"

echo "✓ Llave instalada. Probá: ssh $VPS 'echo ok' (no debería pedir password)"
