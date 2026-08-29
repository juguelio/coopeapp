#!/usr/bin/env bash
# Prueba el comando forzado de la llave de CI SIN tocar el VPS: simula lo que
# sshd pone en $SSH_ORIGINAL_COMMAND y verifica qué acepta y qué rechaza.
#
# Corre en cualquier lado, no necesita red ni servidor:
#     ./scripts/probar-forced-command.sh
#
# Incluye un CONTROL NEGATIVO: al final corre la misma batería contra un
# wrapper roto a propósito y exige que los rechazos se conviertan en
# permisos. Si la batería no distingue el wrapper bueno del roto, no está
# probando nada — y una prueba que no sabe fallar es peor que ninguna, porque
# da tranquilidad falsa.
set -u
cd "$(dirname "$0")/.."
REAL="scripts/vps/ci-forced-command.sh"

# ── banco de pruebas ────────────────────────────────────────────────
# etiqueta | comando que pide el cliente | PERMITE o RECHAZA
CASOS=(
  "rsync a addons (absoluto)|rsync --server -logDtpre.iLsfxCIvu --delete . @HOME@/odoo-coop/addons/|PERMITE"
  "rsync a addons (con ~)|rsync --server -logDtpre.iLsfxCIvu --delete . ~/odoo-coop/addons/|PERMITE"
  "deploy lista valida|deploy coop_construction,coop_portal|PERMITE"
  "shell pelada|id|RECHAZA"
  "bash interactivo|/bin/bash -i|RECHAZA"
  "docker (= root)|docker run -v /:/host alpine chroot /host sh|RECHAZA"
  "leer una llave privada|cat /home/odoo-admin/.ssh/id_rsa|RECHAZA"
  "rsync fuera de addons|rsync --server -e.x . /etc/nginx/|RECHAZA"
  "rsync al home|rsync --server -e.x . @HOME@/|RECHAZA"
  "rsync --daemon|rsync --daemon --config=/tmp/x|RECHAZA"
  "deploy con ; inyectado|deploy coop_portal;id|RECHAZA"
  "deploy con backticks|deploy \`id\`|RECHAZA"
  "deploy con comando pegado|deploy coop_portal id|RECHAZA"
  "deploy vacio|deploy |RECHAZA"
  "comando vacio||RECHAZA"
)

# ── banco de arena ──────────────────────────────────────────────────
montar() {
  local wrapper="$1" raiz="$2"
  rm -rf "$raiz"; mkdir -p "$raiz/odoo-coop/addons" "$raiz/bin"
  cp "$wrapper" "$raiz/odoo-coop/w.sh"
  printf '#!/bin/bash\necho "DEPLOY-OK $1"\n' > "$raiz/odoo-coop/deploy-modulos.sh"
  printf '#!/bin/bash\necho "RSYNC-OK $*"\n' > "$raiz/bin/rsync"
  chmod +x "$raiz/odoo-coop/deploy-modulos.sh" "$raiz/bin/rsync"
}

correr() {
  local raiz="$1" cmd="$2"
  ( export HOME="$raiz" PATH="$raiz/bin:$PATH"
    SSH_ORIGINAL_COMMAND="$cmd" bash "$raiz/odoo-coop/w.sh" ) >/dev/null 2>&1
}

bateria() {          # $1 = wrapper, $2 = raiz, $3 = "estricto"|"laxo"
  local fallas=0 raiz="$2"
  montar "$1" "$raiz"
  for caso in "${CASOS[@]}"; do
    IFS='|' read -r etiqueta cmd espera <<< "$caso"
    cmd="${cmd//@HOME@/$raiz}"
    correr "$raiz" "$cmd" && obtenido=PERMITE || obtenido=RECHAZA
    if [ "$3" = "estricto" ]; then
      if [ "$obtenido" = "$espera" ]; then
        printf '  ✓ %-32s %s\n' "$etiqueta" "$obtenido"
      else
        printf '  ✗ %-32s %s (esperaba %s)\n' "$etiqueta" "$obtenido" "$espera"
        fallas=$((fallas+1))
      fi
    else
      # modo laxo: solo interesa si el wrapper roto deja pasar los rechazos
      [ "$espera" = "RECHAZA" ] && [ "$obtenido" = "PERMITE" ] && fallas=$((fallas+1))
    fi
  done
  return $fallas
}

echo "── El wrapper real ──"
bateria "$REAL" /tmp/fc-real estricto
FALLAS=$?

echo
echo "── Control negativo: un wrapper roto tiene que dar rojo ──"
# El bug clásico: la guarda final no rechaza, ejecuta.
# No usamos `head -n -3`: esa forma existe en GNU head pero macOS la rechaza.
# Cortamos por el encabezado de la guarda final, que además deja explícito qué
# parte del wrapper se está rompiendo para el control negativo.
sed '/^# ── 3\. cualquier otra cosa/,$d' "$REAL" > /tmp/fc-roto.sh
echo 'exec $CMD' >> /tmp/fc-roto.sh
bateria /tmp/fc-roto.sh /tmp/fc-roto laxo
COLADOS=$?
if [ "$COLADOS" -gt 0 ]; then
  echo "  ✓ con la guarda rota se colaron $COLADOS comandos: la prueba distingue"
else
  echo "  ✗ el wrapper roto tampoco deja pasar nada: LA PRUEBA NO PRUEBA NADA"
  FALLAS=$((FALLAS+1))
fi

echo
if [ "$FALLAS" -eq 0 ]; then
  echo "✓ Todo bien. Esto NO reemplaza probarlo contra el VPS:"
  echo "  ./scripts/verificar-llave-ci.sh"
  exit 0
fi
echo "✗ $FALLAS problema(s)."
exit 1
