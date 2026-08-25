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

echo "⚠  Postgres es COMPARTIDO con producción (mismo contenedor odoo-coop-db)."
echo "   Los datos de coop_piloto no se tocan, pero el motor se carga."
echo "   Mejor no correr esto mientras los socios están usando la app."
echo

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

# El repo en la Mac tiene los archivos en 600 (el puente de Cowork los monta
# así) y scp conserva ese modo. Odoo corre como el usuario `odoo` dentro del
# contenedor: sin esto, no puede ni leer los __manifest__.py y falla con
# PermissionError antes de correr un solo test.
echo "→ Abriendo permisos de lectura en addons-test..."
ssh "${SSH_OPTS[@]}" "$VPS" "chmod -R u+rwX,go+rX ~/odoo-coop/addons-test"

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

# Dos fases, y la separación es el punto:
#
# Fase 1 instala los módulos SIN tests. Fase 2 corre SOLO nuestros tests, con
# --test-tags. La primera versión de este script hacía `-i ... --test-enable`
# en un solo paso, y eso corre la suite entera de Odoo: 1044 tests de `base`
# más los de `web`, que levantan un servidor HTTP de verdad. Resultado: 6
# fallas y 2 errores del core de Odoo que no tienen nada que ver con nosotros,
# y Postgres caído en recovery mode arrastrando todo.
#
# Postgres es COMPARTIDO con producción (mismo contenedor odoo-coop-db). Los
# datos de coop_piloto no se tocan, pero cargar el motor a fondo sí la afecta.
# Correr solo nuestros tests no es una optimización: es no voltear la app.

echo "→ Fase 1: instalando $MODULOS (sin tests)..."
set +e
ssh "${SSH_OPTS[@]}" "$VPS" "
  cd ~/odoo-coop
  docker compose run --rm \
    -v \$HOME/odoo-coop/addons-test:/mnt/addons-test \
    odoo odoo -d $DB_TEST \
      --addons-path=/mnt/addons-test,$ADDONS_PATH \
      -i $MODULOS --without-demo=all --workers 0 --stop-after-init 2>&1
" | tail -5
RC_INSTALL=${PIPESTATUS[0]}
set -e
if [ "$RC_INSTALL" -ne 0 ]; then
  echo "✗ No se pudieron instalar los módulos (código $RC_INSTALL)."
  ssh "${SSH_OPTS[@]}" "$VPS" "docker exec odoo-coop-db dropdb -U odoo --if-exists $DB_TEST" || true
  exit "$RC_INSTALL"
fi

# --test-tags /modulo restringe a los tests DEFINIDOS en ese módulo.
TAGS="$(echo "$MODULOS" | tr ',' '\n' | sed 's|^|/|' | paste -sd, -)"
echo "→ Fase 2: corriendo SOLO nuestros tests ($TAGS)..."
set +e
ssh "${SSH_OPTS[@]}" "$VPS" "
  cd ~/odoo-coop
  docker compose run --rm \
    -v \$HOME/odoo-coop/addons-test:/mnt/addons-test \
    odoo odoo -d $DB_TEST \
      --addons-path=/mnt/addons-test,$ADDONS_PATH \
      -u $MODULOS --test-enable --test-tags '$TAGS' \
      --workers 0 --stop-after-init --log-level=test 2>&1
" | tee /tmp/coopeapp-test.log
RC=${PIPESTATUS[0]}
set -e

echo "→ Borrando la base de test..."
ssh "${SSH_OPTS[@]}" "$VPS" "docker exec odoo-coop-db dropdb -U odoo --if-exists $DB_TEST" || true

echo

# La linea autoritativa de Odoo es el resumen por modulo:
#   Module coop_construction: 0 failures, 0 errors of 19 tests
# Grepear ERROR/FAIL suelto trae ruido del log que no son tests.
RESUMEN="$(grep -oE 'Module [a-z_]+: [0-9]+ failures?, [0-9]+ errors? of [0-9]+ tests' /tmp/coopeapp-test.log || true)"

if [ -z "$RESUMEN" ]; then
  echo "✗ NO CORRIO NINGUN TEST."
  echo "  Odoo no imprimio ningun resumen por modulo. Un log sin tests es peor"
  echo "  que uno en rojo: parece que todo anda."
  echo "  Log: /tmp/coopeapp-test.log"
  grep -E '(CRITICAL|Traceback|PermissionError|OperationalError)' /tmp/coopeapp-test.log | head -20
  exit 1
fi

echo "Resumen por modulo:"
echo "$RESUMEN" | sed 's/^/  /'
echo

if echo "$RESUMEN" | grep -qvE ': 0 failures?, 0 errors?'; then
  echo "✗ HAY TESTS EN ROJO:"
  echo "$RESUMEN" | grep -vE ': 0 failures?, 0 errors?' | sed 's/^/  /'
  echo
  echo "Detalle (log completo en /tmp/coopeapp-test.log):"
  grep -E '^[0-9-]+ .*(FAIL|ERROR): ' /tmp/coopeapp-test.log | head -30
  exit 1
fi

if [ "$RC" -ne 0 ]; then
  echo "✗ Los tests pasaron pero Odoo salio con codigo $RC. Revisa el log."
  exit "$RC"
fi

echo "✓ Todos los tests pasaron. Produccion no se toco."
