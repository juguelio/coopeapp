#!/usr/bin/env bash
# Configura acceso SSH SIN password al VPS (una sola vez).
# Idempotente: se puede correr de nuevo sin romper nada.
#
# Hace 3 cosas:
#   1. crea una llave ed25519 en la Mac si no existe
#   2. instala la pubkey en el VPS Y corrige los permisos del lado server
#      (la causa #1 de "la llave la rechaza y cae a password" es StrictModes:
#       el home o ~/.ssh quedan group-writable y sshd ignora la llave)
#   3. deja un alias "coopeapp-vps" en ~/.ssh/config (deploy y ssh sin -i ni IP)
#
# Te va a pedir la password del VPS 1 vez (para instalar la llave). Después, nunca más.
set -euo pipefail

VPS_USER="odoo-admin"
VPS_HOST="178.105.15.189"
VPS="$VPS_USER@$VPS_HOST"
KEY="$HOME/.ssh/id_ed25519"

# ── 1. llave en la Mac ───────────────────────────────────────────────
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if [ ! -f "$KEY" ]; then
  echo "→ Generando llave ed25519..."
  ssh-keygen -t ed25519 -N "" -C "coopeapp-deploy" -f "$KEY"
fi
PUB="$(cat "$KEY.pub")"

# ── 2. instalar pubkey + arreglar permisos server-side (1 password) ──
# Forzamos password en este paso (PubkeyAuthentication=no) porque la llave
# todavía no funciona; así no falla antes de instalarla.
echo "→ Instalando la llave y corrigiendo permisos en el VPS (te pide la password)..."
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password "$VPS" "
  set -e
  install -d -m 700 ~/.ssh
  touch ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
  grep -qxF '$PUB' ~/.ssh/authorized_keys || echo '$PUB' >> ~/.ssh/authorized_keys
  chmod 700 ~/.ssh
  # StrictModes: el home NO puede ser group/other-writable
  chmod g-w,o-w ~
  chown -R \$(id -un):\$(id -gn) ~/.ssh
  echo '   permisos quedaron:'; ls -ld ~ ~/.ssh ~/.ssh/authorized_keys
"

# ── 3. alias en ~/.ssh/config de la Mac ──────────────────────────────
if ! grep -q "Host coopeapp-vps" ~/.ssh/config 2>/dev/null; then
  echo "→ Agregando alias 'coopeapp-vps' a ~/.ssh/config..."
  cat >> ~/.ssh/config <<EOF

Host coopeapp-vps
    HostName $VPS_HOST
    User $VPS_USER
    IdentityFile $KEY
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
    ServerAliveInterval 30
EOF
  chmod 600 ~/.ssh/config
fi

# ── 4. verificar login por clave ─────────────────────────────────────
echo "→ Verificando login por clave (NO debería pedir password)..."
if ssh -o BatchMode=yes -o ConnectTimeout=10 "$VPS" 'echo OK_SIN_PASSWORD' >/dev/null 2>&1; then
  echo "✓ Listo: SSH sin password funciona. Ya podés usar ./scripts/deploy.sh sin tipear nada."
else
  echo "✗ Todavía pide password. Corré:  ./scripts/diagnose-ssh.sh"
  echo "  (suele ser permisos del home o una opción de sshd_config)"
  exit 1
fi
