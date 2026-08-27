#!/bin/bash
# Comando forzado para la llave de CI. Va en el VPS, en
# ~/odoo-coop/ci-forced-command.sh, referenciado desde authorized_keys:
#
#   restrict,command="/home/odoo-admin/odoo-coop/ci-forced-command.sh" ssh-ed25519 AAAA... coopeapp-ci-deploy
#
# Sin esto, la llave de CI abre una shell completa como odoo-admin — que por
# estar en el grupo docker es root. O sea: la llave que vive en los secrets de
# GitHub es hoy una llave de root. Ver docs/seguridad-vps.md.
#
# Con `command=`, lo que el cliente pide NO se ejecuta: llega como dato en
# $SSH_ORIGINAL_COMMAND y este script decide.
set -euo pipefail
set -f          # sin globbing: $CMD nunca expande comodines

CMD="${SSH_ORIGINAL_COMMAND:-}"
LOG="$HOME/odoo-coop/ci-deploy.log"
ADDONS="$HOME/odoo-coop/addons"

registrar() { printf '%s  %-8s  %s\n' "$(date -Is)" "$1" "$CMD" >> "$LOG"; }

# ── 1. el rsync que sube los addons ──────────────────────────────────
# El cliente manda algo como:
#   rsync --server -logDtpre.iLsfxCIvu --delete . /home/odoo-admin/odoo-coop/addons/
# Se acepta solo si es --server (nunca --daemon) y el destino cae adentro de
# addons/. `exec $CMD` sin comillas hace word-splitting, que es lo que rsync
# necesita; NO reinterpreta metacaracteres, así que un `;` en el string queda
# como argumento de rsync y no abre un comando nuevo.
if [ "${CMD%% *}" = "rsync" ]; then
  case " $CMD " in
    *" --daemon "*) registrar RECHAZO; echo "rsync --daemon no permitido" >&2; exit 1 ;;
  esac
  case "$CMD" in
    "rsync --server "*)
      # el destino tiene que ser addons/ — se acepta absoluto o con ~
      case "$CMD" in
        *" $ADDONS/"*|*" ~/odoo-coop/addons/"*|*" odoo-coop/addons/"*)
          registrar RSYNC
          exec $CMD ;;
      esac
      registrar RECHAZO
      echo "rsync solo puede escribir en odoo-coop/addons/" >&2; exit 1 ;;
  esac
  registrar RECHAZO
  echo "solo se acepta 'rsync --server'" >&2; exit 1
fi

# ── 2. el deploy ─────────────────────────────────────────────────────
# Formato exacto: deploy modulo1,modulo2
# La lista se valida acá y NO se interpola en ningún shell remoto.
if [ "${CMD%% *}" = "deploy" ]; then
  MODULOS="${CMD#deploy }"
  case "$MODULOS" in
    ""|"deploy"|*[!A-Za-z0-9_,-]*)
      registrar RECHAZO
      echo "lista de módulos inválida (solo letras, números, _ - y coma)" >&2
      exit 1 ;;
  esac
  registrar DEPLOY
  exec "$HOME/odoo-coop/deploy-modulos.sh" "$MODULOS"
fi

# ── 3. cualquier otra cosa ───────────────────────────────────────────
registrar RECHAZO
echo "Esta llave solo puede subir addons y deployar. Comando no permitido." >&2
exit 1
