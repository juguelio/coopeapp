#!/usr/bin/env bash
# Acota la llave de CI a lo único que necesita hacer: subir addons y deployar.
# Hoy esa llave abre una shell completa como odoo-admin, que por estar en el
# grupo docker es root. Ver docs/seguridad-vps.md.
#
#   ./scripts/aplicar-hardening-ci.sh           # acota la llave actual
#   ./scripts/aplicar-hardening-ci.sh --rotar   # además genera una llave nueva
#
# Tu llave PERSONAL (alias coopeapp-vps) no se toca: es la red de seguridad.
set -euo pipefail

ROTAR=0
[ "${1:-}" = "--rotar" ] && ROTAR=1

VPS="coopeapp-vps"
VPS_USER="odoo-admin"
VPS_HOST="178.105.15.189"
CI_KEY="$HOME/.ssh/coopeapp_ci"
MARCA="coopeapp-ci-deploy"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FORZADO="/home/$VPS_USER/odoo-coop/ci-forced-command.sh"

echo "→ Probando el wrapper en local antes de instalarlo..."
bash "$REPO/scripts/probar-forced-command.sh" >/dev/null || {
  echo "✗ El wrapper no pasa sus propias pruebas. No se instala nada."; exit 1; }
echo "  ok"

echo "→ Verificando que tu llave personal entra (red de seguridad)..."
ssh -o BatchMode=yes "$VPS" true || {
  echo "✗ No entrás con la llave personal. NO sigas: si acotás la de CI ahora"
  echo "  y algo sale mal, te quedás sin forma de entrar."; exit 1; }
echo "  ok"

if [ "$ROTAR" -eq 1 ]; then
  echo "→ Generando llave de CI nueva..."
  mv -f "$CI_KEY" "$CI_KEY.viejo.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
  mv -f "$CI_KEY.pub" "$CI_KEY.pub.viejo" 2>/dev/null || true
  ssh-keygen -t ed25519 -N "" -C "$MARCA" -f "$CI_KEY"
fi

[ -f "$CI_KEY.pub" ] || { echo "✗ No existe $CI_KEY.pub. Corré con --rotar."; exit 1; }
PUB="$(cat "$CI_KEY.pub")"

echo "→ Instalando los scripts en el VPS..."
scp -q "$REPO/scripts/vps/ci-forced-command.sh" \
       "$REPO/scripts/vps/deploy-modulos.sh" \
       "$VPS:~/odoo-coop/"
ssh "$VPS" "chmod 700 ~/odoo-coop/ci-forced-command.sh ~/odoo-coop/deploy-modulos.sh"

echo "→ Reescribiendo authorized_keys (solo la línea de CI)..."
ssh "$VPS" "
  set -e
  cd ~/.ssh
  cp authorized_keys authorized_keys.bak.\$(date +%Y%m%d%H%M%S)
  # Se saca CUALQUIER línea que tenga la marca de CI, restringida o no.
  grep -v '$MARCA' authorized_keys > /tmp/ak.nuevo || true
  echo 'restrict,command=\"$FORZADO\" $PUB' >> /tmp/ak.nuevo
  install -m 600 /tmp/ak.nuevo authorized_keys
  rm -f /tmp/ak.nuevo
  echo '  líneas en authorized_keys:' \$(wc -l < authorized_keys)
"

echo "→ Confirmando que tu llave personal SIGUE entrando..."
ssh -o BatchMode=yes "$VPS" true || {
  echo "✗ ¡Perdiste el acceso personal! Restaurá desde ~/.ssh/authorized_keys.bak.*"
  echo "  (si todavía tenés una sesión abierta, usala YA)"; exit 1; }
echo "  ok"

if [ "$ROTAR" -eq 1 ] && command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  echo "→ Actualizando el secret de GitHub con la llave nueva..."
  gh secret set VPS_SSH_PRIVATE_KEY < "$CI_KEY"
elif [ "$ROTAR" -eq 1 ]; then
  echo "⚠  Rotaste la llave pero no pude actualizar GitHub (falta gh o no está"
  echo "   autenticado). Hacelo a mano o el auto-deploy va a fallar:"
  echo "     gh secret set VPS_SSH_PRIVATE_KEY < $CI_KEY"
fi

echo
echo "→ Verificando que la llave de CI ya NO puede abrir una shell..."
"$REPO/scripts/verificar-llave-ci.sh"
