#!/bin/bash
# Lo único que la llave de CI puede ejecutar además del rsync. Va en el VPS,
# en ~/odoo-coop/deploy-modulos.sh. Se invoca desde ci-forced-command.sh, que
# ya validó el formato de la lista.
set -euo pipefail

MODULOS="${1:?falta la lista de módulos}"
DB="coop_piloto"

# Se revalida acá también: este script no puede confiar en que siempre lo
# llame el wrapper. Una validación que solo existe en el llamador es una
# validación que un día no corre.
case "$MODULOS" in
  *[!A-Za-z0-9_,-]*) echo "✗ lista de módulos inválida" >&2; exit 1 ;;
esac

cd "$HOME/odoo-coop"

for m in ${MODULOS//,/ }; do
  [ -d "addons/$m" ] || { echo "✗ addons/$m no existe" >&2; exit 1; }
  find "addons/$m" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
done

echo "→ Actualizando $MODULOS en $DB..."
docker compose run --rm odoo odoo -u "$MODULOS" -d "$DB" --stop-after-init
docker compose restart odoo
echo "✓ Deploy de $MODULOS completo"
