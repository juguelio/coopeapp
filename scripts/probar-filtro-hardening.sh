#!/usr/bin/env bash
# Prueba OFFLINE del filtro de authorized_keys de aplicar-hardening-ci.sh.
# No toca el VPS ni la red.
#
# El 2026-08-27 el hardening borró la llave personal porque filtraba por el
# COMENTARIO ('coopeapp-ci-deploy'), asumiendo que solo la de CI lo tenía. La
# personal en el server lo compartía, y se fue con el grep -v.
#
# Este test arma exactamente ese authorized_keys venenoso —personal y CI con el
# MISMO comentario— y exige que el filtro nuevo (por base64) conserve la
# personal. El CONTROL NEGATIVO corre el filtro viejo (por comentario) sobre el
# mismo archivo y exige que SÍ la borre: si el test no distingue el filtro bueno
# del roto, no está probando nada.
set -u

FORZADO="/home/odoo-admin/odoo-coop/ci-forced-command.sh"

# base64 inventados pero con la forma real (segundo token de una ed25519).
CI_B64="AAAAC3NzaC1lZDI1NTE5AAAAICIkeyCIkeyCIkeyCIkeyCIkeyCIkeyCIkeyCI0000"
PERSONAL_B64="AAAAC3NzaC1lZDI1NTE5AAAAIPERSONALpersonalPERSONALpersonalPE1111"

# authorized_keys venenoso: la personal comparte el comentario con la de CI.
AK="$(mktemp)"
cat > "$AK" <<EOF
ssh-ed25519 $PERSONAL_B64 coopeapp-ci-deploy
command="/algo/viejo" ssh-ed25519 $CI_B64 coopeapp-ci-deploy
EOF

fallas=0

# ── filtro NUEVO: por el material exacto (base64) ────────────────────
nuevo="$(mktemp)"
grep -Fv "$CI_B64" "$AK" > "$nuevo" || true
printf 'restrict,command="%s" ssh-ed25519 %s coopeapp-ci-deploy\n' "$FORZADO" "$CI_B64" >> "$nuevo"

if grep -Fq "$PERSONAL_B64" "$nuevo"; then
  echo "  ✓ filtro por base64: la llave personal SOBREVIVE"
else
  echo "  ✗ filtro por base64: BORRÓ la personal — el fix no sirve"
  fallas=$((fallas+1))
fi
if [ "$(grep -Fc "$CI_B64" "$nuevo")" = 1 ]; then
  echo "  ✓ filtro por base64: queda exactamente UNA línea de CI"
else
  echo "  ✗ filtro por base64: no quedó exactamente una línea de CI"
  fallas=$((fallas+1))
fi
if grep -q 'restrict,command=' "$nuevo" && ! grep -q '"/algo/viejo"' "$nuevo"; then
  echo "  ✓ filtro por base64: la de CI quedó restringida y sin la vieja"
else
  echo "  ✗ filtro por base64: la línea de CI no quedó bien"
  fallas=$((fallas+1))
fi

# ── CONTROL NEGATIVO: el filtro viejo (por comentario) DEBE romper ───
viejo="$(mktemp)"
grep -v 'coopeapp-ci-deploy' "$AK" > "$viejo" || true
if grep -Fq "$PERSONAL_B64" "$viejo"; then
  echo "  ✗ control negativo: el filtro VIEJO conservó la personal —"
  echo "    entonces este test no distingue el bueno del roto, no prueba nada"
  fallas=$((fallas+1))
else
  echo "  ✓ control negativo: el filtro viejo SÍ borra la personal (como el 08-27)"
fi

rm -f "$AK" "$nuevo" "$viejo"

echo
if [ "$fallas" -eq 0 ]; then
  echo "✓ El filtro por base64 conserva la personal; el viejo la borraba."
  exit 0
fi
echo "✗ $fallas problema(s) en el filtro de authorized_keys."
exit 1
