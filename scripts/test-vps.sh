#!/usr/bin/env bash
# Corre los tests de Odoo en el VPS, SIN TOCAR PRODUCCIÓN.
#
# Por qué existe: el docker-compose vive en el VPS (~/odoo-coop), no en el
# repo, así que `docker compose` desde la Mac no encuentra configuración. Y
# correr los tests contra `coop_piloto` sería correrlos contra producción: el
# `-u` la actualiza de verdad.
#
# Este script sube el código a un directorio aparte, crea una base descartable,
# instala los módulos ahí con los tests activados, y borra la base al terminar.
# `coop_piloto` no se toca en ningún paso.
#
# Uso: ./scripts/test-vps.sh [modulo1,modulo2]
set -euo pipefail

MODULOS="${1:-coop_construction,coop_assembly,coop_portal}"
VPS="coopeapp-vps"
DB_TEST="coop_test_ci"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$DB_TEST" = "coop_piloto" ]; then
  echo "✗ La base de test no puede ser producción."; exit 1
fi

CTL="/tmp/coopeapp-ssh-%r@%h:%p"
SSH_OPTS=(-o "ControlMaster=auto" -o "ControlPath=$CTL" -o "ControlPersist=120")
trap 'ssh "${SSH_OPTS[@]}" -O exit "$VPS" 2>/dev/null || true' EXIT

echo "→ Subiendo addons a ~/odoo-coop/addons-test/ (NO pisa los de producción)..."
ssh "${SSH_OPTS[@]}" "$VPS" "mkdir -p ~/odoo-coop/addons-test && rm -rf ~/odoo-coop/addons-test/*"
IFS=',' read -ra LISTA <<< "$MODULOS"
# se suben TODOS los addons del repo: los módulos dependen entre sí
for d in "$REPO"/addons/*/; do
  m="$(basename "$d")"
  find "$d" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  scp "${SSH_OPTS[@]}" -rq "$d" "$VPS:~/odoo-coop/addons-test/"
done

echo "→ Averiguando el addons_path real del contenedor..."
# No lo inventamos: se lee del odoo.conf que está corriendo. Si no se puede
# leer, el script para — es mejor no correr que correr con una ruta inventada
# y que los tests "pasen" porque no encontraron los módulos.
ADDONS_PATH="$(ssh "${SSH_OPTS[@]}" "$VPS" "
  docker exec odoo-coop-app sh -c '
    for f in /etc/odoo/odoo.conf /etc/odoo.conf \$ODOO_RC; do
      [ -f \"\$f\" ] && grep -iE \"^[[:space:]]*addons_path\" \"\$f\" && exit 0
    done' 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' '
")"
if [ -z "$ADDONS_PATH" ]; then
  echo "✗ No se pudo leer addons_path del contenedor odoo-coop-app."
  echo "  Miralo a mano y pasalo por la variable ADDONS_PATH:"
  echo "    ssh $VPS \"docker exec odoo-coop-app cat /etc/odoo/odoo.conf\""
  exit 1
fi
echo "  addons_path = $ADDONS_PATH"

echo "→ Creando base descartable '$DB_TEST'..."
ssh "${SSH_OPTS[@]}" "$VPS" "
  docker exec odoo-coop-db dropdb -U odoo --if-exists $DB_TEST
  docker exec odoo-coop-db createdb -U odoo -O odoo $DB_TEST
"

echo "→ Instalando $MODULOS con tests activados..."
set +e
ssh "${SSH_OPTS[@]}" "$VPS" "
  cd ~/odoo-coop
  docker compose run --rm \
    -v \$HOME/odoo-coop/addons-test:/mnt/addons-test \
    odoo odoo -d $DB_TEST \
      --addons-path=/mnt/addons-test,$ADDONS_PATH \
      -i $MODULOS --test-enable --without-demo=all --stop-after-init \
      --log-level=test 2>&1
" | tee /tmp/coopeapp-test.log
RC=${PIPESTATUS[0]}
set -e

echo "→ Borrando la base de test..."
ssh "${SSH_OPTS[@]}" "$VPS" "docker exec odoo-coop-db dropdb -U odoo --if-exists $DB_TEST" || true

echo
if grep -qE '^[0-9-]+ .* (ERROR|FAIL)' /tmp/coopeapp-test.log; then
  echo "✗ HAY TESTS EN ROJO. Log completo: /tmp/coopeapp-test.log"
  grep -E '(ERROR|FAIL|Traceback)' /tmp/coopeapp-test.log | head -40
  exit 1
fi
if [ "$RC" -ne 0 ]; then
  echo "✗ Odoo salió con código $RC. Log: /tmp/coopeapp-test.log"; exit "$RC"
fi
echo "✓ Todos los tests pasaron. Producción no se tocó."
