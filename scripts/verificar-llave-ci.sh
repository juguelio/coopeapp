#!/usr/bin/env bash
# ¿La llave de CI puede hacer algo más que su trabajo?
#
# Corre CONTRA EL VPS de verdad. Da rojo si la llave todavía abre una shell,
# porque de eso se trata: un chequeo que no sabe fallar no es un chequeo.
set -uo pipefail

CI_KEY="${CI_KEY:-$HOME/.ssh/coopeapp_ci}"
VPS_USER="${VPS_USER:-odoo-admin}"
VPS_HOST="${VPS_HOST:-178.105.15.189}"
# -F /dev/null + IdentitiesOnly: probar EXACTAMENTE la de CI, sin que el ssh
# config meta otra llave. -o ControlPath=none: sin reuso de conexión, que da
# "verde" sin autenticar. Las dos cosas contaminaron el diagnóstico del 08-27.
SSH=(ssh -F /dev/null -i "$CI_KEY" -o IdentitiesOnly=yes -o ControlPath=none \
  -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
  "$VPS_USER@$VPS_HOST")

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
echo "── Y SÍ tiene que poder (el camino de deploy está vivo) ──"
# No se grepea un texto de más abajo ("no existe"), que es frágil y fue el falso
# rojo del 08-27. Se distingue por DÓNDE se rechaza cada caso:
#   (a) lista INVÁLIDA  → la corta el WRAPPER  ("lista de módulos inválida")
#   (b) lista VÁLIDA    → pasa el wrapper y la corta deploy-modulos.sh ("no existe")
# Que (a) y (b) fallen en lugares DISTINTOS prueba que el deploy atraviesa el
# wrapper hasta el script. Si los dos dieran el mismo mensaje, no probaría el paso.
inval="$("${SSH[@]}" "deploy no,vale;esto" 2>&1 || true)"
valid="$("${SSH[@]}" "deploy modulo_que_no_existe_zzz" 2>&1 || true)"

if grep -qi "inválida\|invalida" <<< "$inval"; then
  echo "  ✓ (a) lista inválida: la rechaza el wrapper"
else
  echo "  ✗ (a) lista inválida: el wrapper no la cortó — respuesta: ${inval:0:100}"
  fallas=$((fallas+1))
fi
if grep -q "no existe" <<< "$valid"; then
  echo "  ✓ (b) lista válida: atraviesa el wrapper y llega a deploy-modulos.sh"
else
  echo "  ✗ (b) lista válida: no llegó al script — el auto-deploy va a fallar"
  [ -n "$valid" ] && echo "    respuesta: ${valid:0:120}"
  fallas=$((fallas+1))
fi

echo
if [ "$fallas" -eq 0 ]; then
  echo "✓ La llave de CI está acotada."
  exit 0
fi
echo "✗ $fallas problema(s). Revisá los rechazos y el camino de deploy arriba."
exit 1
