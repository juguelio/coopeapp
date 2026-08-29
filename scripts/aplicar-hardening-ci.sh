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
PERSONAL_KEY="${PERSONAL_KEY:-$HOME/.ssh/id_ed25519}"
MARCA="coopeapp-ci-deploy"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FORZADO="/home/$VPS_USER/odoo-coop/ci-forced-command.sh"

# No usamos el alias coopeapp-vps para esta prueba: hoy ese alias también
# enumera coopeapp_ci. Después de instalar la restricción, SSH puede entrar con
# la CI y ejecutar `true` dentro del wrapper, lo que no demuestra que la llave
# personal funcione. -F /dev/null evita heredar IdentityFile del ssh config.
# -o ControlPath=none es OBLIGATORIO: sin eso ssh reusa una conexión abierta y
# da "verde" sin volver a autenticar — exactamente cómo se ocultó el lockout
# del 08-27, cuando el post-chequeo pasó sobre una personal ya rota.
SSH_PERSONAL=(ssh -F /dev/null -i "$PERSONAL_KEY" -o IdentitiesOnly=yes \
  -o ControlPath=none -o BatchMode=yes -o ConnectTimeout=10 "$VPS_USER@$VPS_HOST")

# El acceso no se prueba con `true` (exit 0 no distingue una shell de un
# forced-command que igual sale 0): se exige un token concreto por stdout, que
# solo puede imprimir una shell real y sin restricción.
personal_tiene_shell() {
  [ "$("${SSH_PERSONAL[@]}" 'echo SHELL_OK' 2>/dev/null)" = "SHELL_OK" ]
}

echo "→ Probando el wrapper en local antes de instalarlo..."
bash "$REPO/scripts/probar-forced-command.sh" >/dev/null || {
  echo "✗ El wrapper no pasa sus propias pruebas. No se instala nada."; exit 1; }
echo "  ok"

echo "→ Probando el filtro de authorized_keys en local (que conserve la personal)..."
bash "$REPO/scripts/probar-filtro-hardening.sh" >/dev/null || {
  echo "✗ El filtro de authorized_keys no pasa sus pruebas. No se instala nada."; exit 1; }
echo "  ok"

echo "→ Verificando que tu llave personal entra (red de seguridad)..."
personal_tiene_shell || {
  echo "✗ No entrás con la llave personal (no imprimió SHELL_OK). NO sigas: si"
  echo "  acotás la de CI ahora y algo sale mal, te quedás sin forma de entrar."; exit 1; }
echo "  ok"

if [ "$ROTAR" -eq 1 ]; then
  echo "→ Generando llave de CI nueva..."
  mv -f "$CI_KEY" "$CI_KEY.viejo.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
  mv -f "$CI_KEY.pub" "$CI_KEY.pub.viejo" 2>/dev/null || true
  ssh-keygen -t ed25519 -N "" -C "$MARCA" -f "$CI_KEY"
fi

[ -f "$CI_KEY.pub" ] || { echo "✗ No existe $CI_KEY.pub. Corré con --rotar."; exit 1; }
[ -f "$PERSONAL_KEY.pub" ] || { echo "✗ No existe $PERSONAL_KEY.pub — no puedo garantizar que la personal sobreviva. Aborto."; exit 1; }
PUB="$(cat "$CI_KEY.pub")"
# El campo base64 (segundo token) es lo ÚNICO que identifica una llave sin
# ambigüedad. El comentario se comparte por accidente; filtrar por él fue lo que
# borró la llave personal el 2026-08-27. Filtramos por esto, nunca por la marca.
CI_B64="$(awk '{print $2}' "$CI_KEY.pub")"
PERSONAL_B64="$(awk '{print $2}' "$PERSONAL_KEY.pub")"
[ -n "$CI_B64" ] && [ -n "$PERSONAL_B64" ] || { echo "✗ No pude extraer el material de las llaves. Aborto."; exit 1; }

echo "→ Instalando los scripts en el VPS..."
scp -q "$REPO/scripts/vps/ci-forced-command.sh" \
       "$REPO/scripts/vps/deploy-modulos.sh" \
       "$VPS:~/odoo-coop/"
ssh "$VPS" "chmod 700 ~/odoo-coop/ci-forced-command.sh ~/odoo-coop/deploy-modulos.sh"

echo "→ Reescribiendo authorized_keys (solo la línea de CI)..."
ssh "$VPS" "
  set -euo pipefail
  cd ~/.ssh
  cp authorized_keys authorized_keys.bak.\$(date +%Y%m%d%H%M%S)
  # Se saca CUALQUIER línea con el material EXACTO de la llave de CI (base64),
  # restringida o no. NUNCA por el comentario: eso borró la personal el 08-27.
  grep -Fv '$CI_B64' authorized_keys > /tmp/ak.nuevo || true
  echo 'restrict,command=\"$FORZADO\" $PUB' >> /tmp/ak.nuevo
  # GUARDA DURA: si la llave personal no quedó en el archivo nuevo, NO instalar.
  # Sin esto no hay red de seguridad — es exactamente el modo de falla del 08-27.
  if ! grep -Fq '$PERSONAL_B64' /tmp/ak.nuevo; then
    echo '✗ ABORTO: la llave personal no está en el authorized_keys nuevo.' >&2
    echo '  authorized_keys queda intacto. Revisá a mano antes de reintentar.' >&2
    rm -f /tmp/ak.nuevo
    exit 1
  fi
  # Exactamente UNA línea de CI, y solo restringida.
  if [ \"\$(grep -Fc '$CI_B64' /tmp/ak.nuevo)\" != 1 ]; then
    echo '✗ ABORTO: no quedó exactamente una línea de CI.' >&2
    rm -f /tmp/ak.nuevo; exit 1
  fi
  install -m 600 /tmp/ak.nuevo authorized_keys
  rm -f /tmp/ak.nuevo
  echo '  líneas en authorized_keys:' \$(wc -l < authorized_keys)
"

echo "→ Confirmando que tu llave personal SIGUE entrando (shell real, no reuso)..."
personal_tiene_shell || {
  echo "✗ ¡Perdiste el acceso personal! (no imprimió SHELL_OK)"
  echo "  Restaurá desde ~/.ssh/authorized_keys.bak.* — pero OJO: el backup tiene"
  echo "  la llave de CI SIN restringir. Restaurá solo la línea de la personal."
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
