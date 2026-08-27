#!/usr/bin/env bash
# ¿La llave de CI puede hacer algo más que su trabajo?
#
# Corre CONTRA EL VPS de verdad. Da rojo si la llave todavía abre una shell,
# porque de eso se trata: un chequeo que no sabe fallar no es un chequeo.
set -uo pipefail

CI_KEY="${CI_KEY:-$HOME/.ssh/coopeapp_ci}"
VPS_USER="${VPS_USER:-odoo-admin}"
VPS_HOST="${VPS_HOST:-178.105.15.189}"
SSH=(ssh -i "$CI_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$VPS_USER@$VPS_HOST")

[ -f "$CI_KEY" ] || { echo "✗ No encuentro $CI_KEY"; exit 1; }

fallas=0
prohibido() {  # etiqueta, comando
  local salida
  salida="$("${SSH[@]}" "$2" 2>&1)"
  if [ $? -eq 0 ]; then
    echo "  ✗ $1 — LA LLAVE PUDO: ${salida:0:60}"
    fallas=$((fallas+1))
  else
    echo "  ✓ $1 — rechazado"
  fi
}

echo "── La llave de CI NO tiene que poder ──"
prohibido "abrir una shell"        "id"
prohibido "leer authorized_keys"   "cat ~/.ssh/authorized_keys"
prohibido "usar docker (= root)"   "docker ps"
prohibido "escribir fuera de addons" "touch ~/tocado-por-ci"

echo
echo "── Y SÍ tiene que poder ──"
if "${SSH[@]}" "deploy no_existe_este_modulo" 2>&1 | grep -q "no existe"; then
  echo "  ✓ el comando 'deploy' llega al script (rechaza un módulo inexistente)"
else
  echo "  ✗ el comando 'deploy' no llegó — el auto-deploy va a fallar"
  fallas=$((fallas+1))
fi

echo
if [ "$fallas" -eq 0 ]; then
  echo "✓ La llave de CI está acotada."
  exit 0
fi
echo "✗ $fallas problema(s). La llave de CI sigue siendo una llave de root."
exit 1
