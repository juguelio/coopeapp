#!/usr/bin/env bash
# Corre los tests de Odoo en el VPS, SIN TOCAR PRODUCCIÓN.
#
# Por qué existe: el docker-compose vive en el VPS (~/odoo-coop), no en el
# repo, así que `docker compose` desde la Mac no encuentra configuración. Y
# correr los tests contra `coop_piloto` sería correrlos contra producción: el
# `-u` la actualiza de verdad.
#
# Crea una base descartable, instala los módulos ahí con los tests activados y
# borra la base al terminar. `coop_piloto` no se toca en ningún paso.
#
# DOS MODOS:
#
#   ./scripts/test-vps.sh                    ← el normal
#       Usa el código que YA está deployado en ~/odoo-coop/addons. Como el
#       flujo es push → auto-deploy → test, eso es exactamente lo que se
#       quiere probar. No copia nada: sin scp, sin disco duplicado, sin
#       permisos que arreglar.
#
#   ./scripts/test-vps.sh --local [modulos]  ← para probar sin pushear
#       Sube el working tree a ~/odoo-coop/addons-test/. Más lento y ocupa
#       disco, pero permite probar antes de commitear.
#
# Uso: ./scripts/test-vps.sh [--local] [modulo1,modulo2]
set -euo pipefail

LOCAL=0
if [ "${1:-}" = "--local" ]; then LOCAL=1; shift; fi
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

# Barato y local: si hay un xmlid referenciado antes de definirse, la
# instalación desde cero falla igual. Mejor enterarse acá que después de
# subir todo y crear una base.
echo "→ Chequeando el orden de los xmlid (sin red)..."
python3 "$REPO/scripts/check-xml-order.py" || exit 1
echo

# Antes de nada: que el VPS esté sano. Un scp que muere con "Connection
# closed" casi siempre es disco lleno o memoria, no red — y el mensaje no lo
# dice.
echo "→ Chequeando salud del VPS..."
SALUD="$(ssh "${SSH_OPTS[@]}" "$VPS" "
  echo DISCO=\$(df --output=pcent / | tail -1 | tr -dc '0-9')
  echo LIBRE_MB=\$(free -m | awk '/^Mem:/{print \$7}')
")"
DISCO="$(echo "$SALUD" | sed -n 's/^DISCO=//p')"
LIBRE_MB="$(echo "$SALUD" | sed -n 's/^LIBRE_MB=//p')"
echo "  disco usado: ${DISCO}%   ·   memoria disponible: ${LIBRE_MB} MB"
if [ -n "$DISCO" ] && [ "$DISCO" -ge 92 ]; then
  echo "✗ El disco del VPS está al ${DISCO}%. Liberá espacio antes de seguir."
  echo "  Candidatos: ~/odoo-coop/addons-test, dumps viejos en ~/odoo-coop/backups,"
  echo "  imágenes de docker sin usar (docker system df)."
  exit 1
fi
if [ -n "$LIBRE_MB" ] && [ "$LIBRE_MB" -lt 400 ]; then
  echo "⚠  Solo ${LIBRE_MB} MB de memoria disponible. Los tests pueden voltear"
  echo "   Postgres, que es el MISMO que sirve producción. Mejor esperá."
  exit 1
fi
echo

ADDONS_TEST=""
if [ "$LOCAL" -eq 1 ]; then
  echo "→ Modo --local: subiendo el working tree a ~/odoo-coop/addons-test/..."
  # tar por el túnel ssh en vez de scp. Motivos, en orden de importancia:
  #
  #  1. `scp -r` en OpenSSH 9 usa SFTP por debajo, y si el sshd del server no
  #     tiene habilitado el subsistema sftp muere con "Connection closed" a
  #     secas — sin decir por qué. Pasó el 25/08 con el VPS perfectamente sano
  #     (disco 29%, 2.6 GB libres), así que no era ni disco ni memoria.
  #  2. Una sola conexión para todo en vez de una por módulo.
  #  3. Los permisos se arreglan del lado del VPS con un chmod después de
  #     extraer: el repo montado en la Mac tiene los archivos en 600 y Odoo
  #     corre como `odoo`. Antes esto usaba `tar --mode=`, que es sintaxis de
  #     GNU tar: la Mac trae bsdtar y moría con "Option --mode is not
  #     supported", así que el modo --local nunca había funcionado desde acá.
  ssh "${SSH_OPTS[@]}" "$VPS" "mkdir -p ~/odoo-coop/addons-test && rm -rf ~/odoo-coop/addons-test/*"
  find "$REPO/addons" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  if ! tar -C "$REPO/addons" \
        --exclude='__pycache__' --exclude='*.pyc' -czf - . \
      | ssh "${SSH_OPTS[@]}" "$VPS" "tar -C ~/odoo-coop/addons-test -xzf - && chmod -R a+rX ~/odoo-coop/addons-test"; then
    echo "✗ Falló la subida del working tree."
    echo "  Probá el modo normal (sin --local), que no copia nada:"
    echo "    ./scripts/test-vps.sh"
    exit 1
  fi
  ADDONS_TEST="/mnt/addons-test,"
else
  echo "→ Usando el código YA deployado en ~/odoo-coop/addons (sin copiar nada)."
  echo "  (si querés probar cambios sin pushear, usá --local)"
  # addons-test solo lo usa el modo --local. Si quedó de una corrida anterior,
  # está ocupando disco al pedo en un VPS que ya viene justo.
  ssh "${SSH_OPTS[@]}" "$VPS" "
    if [ -d ~/odoo-coop/addons-test ]; then
      echo '  (liberando ~/odoo-coop/addons-test de una corrida anterior:' \
           \$(du -sh ~/odoo-coop/addons-test 2>/dev/null | cut -f1)')'
      rm -rf ~/odoo-coop/addons-test
    fi"
fi
echo

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
HOME_VPS="$(ssh "${SSH_OPTS[@]}" "$VPS" 'echo $HOME')"

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

MOUNT=""
if [ "$LOCAL" -eq 1 ]; then
  MOUNT="-v $HOME_VPS/odoo-coop/addons-test:/mnt/addons-test"
fi

# Fase 0: los tests que NO necesitan Odoo ni base.
#
# `test_foja_parser.py` usa `unittest.TestCase` plano y sin `@tagged` a
# propósito: el parser no importa Odoo y los tests se pueden correr sueltos.
# El costo es que `--test-tags` NO los levanta, así que sus 15 tests nunca
# habían corrido en ninguna de las corridas "completas" — el mismo patrón de
# tests escritos sin ejecutarse. Corren acá, dentro del contenedor, porque
# necesitan `openpyxl`, que Odoo trae y la Mac no.
RUTA_TESTS="/mnt/extra-addons/coop_construction/tests"
if [ "$LOCAL" -eq 1 ]; then RUTA_TESTS="/mnt/addons-test/coop_construction/tests"; fi
echo "→ Fase 0: tests sin base (parser de cómputos)..."
set +e
ssh "${SSH_OPTS[@]}" "$VPS" "
  cd ~/odoo-coop
  docker compose run --rm $MOUNT \
    odoo python3 -m unittest discover -s $RUTA_TESTS -p 'test_foja_parser.py' -v 2>&1
" > /tmp/coopeapp-parser.log 2>&1
RC_PARSER=$?
set -e
PARSER_RES="$(grep -oE '^(OK|FAILED)([^ ]*| \(.*\))' /tmp/coopeapp-parser.log | tail -1)"
PARSER_N="$(grep -oE '^Ran [0-9]+ tests?' /tmp/coopeapp-parser.log | tail -1)"
if [ "$RC_PARSER" -ne 0 ] || [ -z "$PARSER_RES" ]; then
  echo "✗ Los tests del parser fallaron (código $RC_PARSER)."
  echo "  Log: /tmp/coopeapp-parser.log"
  grep -E '^(FAIL|ERROR):' /tmp/coopeapp-parser.log | sed 's/^/  /' | head -20
  grep -A 12 -m 1 'Traceback (most recent call last)' /tmp/coopeapp-parser.log | sed 's/^/  /'
  exit 1
fi
echo "  ${PARSER_N:-?} · $PARSER_RES"
# Cuenta las LINEAS de test salteado, no toda linea con la palabra: el
# resumen "OK (skipped=2)" tambien la trae y hacia contar uno de mas.
SKIPS="$(grep -cE "\\.\\.\\. skipped '" /tmp/coopeapp-parser.log || true)"
if [ "${SKIPS:-0}" -gt 0 ]; then
  echo "  ⚠  $SKIPS salteados (no son verdes, son tests que no corrieron):"
  grep -oE "^test_[^ ]+ \(.*\) \.\.\. skipped '.*'" /tmp/coopeapp-parser.log \
    | sed -E "s/^(test_[^ ]+).*skipped '(.*)'/    \1 — \2/" | head -10
fi
echo

echo "→ Fase 1: instalando $MODULOS (sin tests)..."
set +e
ssh "${SSH_OPTS[@]}" "$VPS" "
  cd ~/odoo-coop
  docker compose run --rm $MOUNT \
    odoo odoo -d $DB_TEST \
      --addons-path=$ADDONS_TEST$ADDONS_PATH \
      -i $MODULOS --without-demo=all --workers 0 --stop-after-init 2>&1
" > /tmp/coopeapp-install.log 2>&1
RC_INSTALL=$?
set -e
if [ "$RC_INSTALL" -ne 0 ]; then
  echo "✗ No se pudieron instalar los módulos (código $RC_INSTALL)."
  echo "  Log completo: /tmp/coopeapp-install.log"
  echo
  # La primera versión hacía `| tail -5` y escondía justamente la causa:
  # se veía el <menuitem> del contexto pero no el ParseError que lo explicaba.
  grep -B 2 -A 12 -E '(ParseError|ValueError|CRITICAL|External ID not found)' \
    /tmp/coopeapp-install.log | head -40 \
    || tail -30 /tmp/coopeapp-install.log
  ssh "${SSH_OPTS[@]}" "$VPS" "docker exec odoo-coop-db dropdb -U odoo --if-exists $DB_TEST" || true
  exit "$RC_INSTALL"
fi

# --test-tags /modulo restringe a los tests DEFINIDOS en ese módulo.
TAGS="$(echo "$MODULOS" | tr ',' '\n' | sed 's|^|/|' | paste -sd, -)"
echo "→ Fase 2: corriendo SOLO nuestros tests ($TAGS)..."
set +e
ssh "${SSH_OPTS[@]}" "$VPS" "
  cd ~/odoo-coop
  docker compose run --rm $MOUNT \
    odoo odoo -d $DB_TEST \
      --addons-path=$ADDONS_TEST$ADDONS_PATH \
      -u $MODULOS --test-enable --test-tags '$TAGS' \
      --workers 0 --stop-after-init --log-level=test 2>&1
" | tee /tmp/coopeapp-test.log
RC=${PIPESTATUS[0]}
set -e

echo "→ Borrando la base de test..."
ssh "${SSH_OPTS[@]}" "$VPS" "docker exec odoo-coop-db dropdb -U odoo --if-exists $DB_TEST" || true

echo

# Odoo reporta el resultado de DOS maneras según cuándo corrieron los tests:
#
#   at_install   → "Module coop_construction: 0 failures, 0 errors of 19 tests"
#   post_install → "odoo.tests.result: 1 failed, 5 error(s) of 11 tests"
#
# La primera version de esto solo miraba la primera forma. El 25/08 corrieron
# 11 tests con 6 en rojo y el script dijo "NO CORRIO NINGUN TEST", que era
# falso y ademas escondia el resultado real. Hay que mirar las dos.

RES_MODULO="$(grep -oE 'Module [a-z_]+: [0-9]+ failures?, [0-9]+ errors? of [0-9]+ tests' /tmp/coopeapp-test.log || true)"
RES_SUITE="$(grep -oE '[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests' /tmp/coopeapp-test.log || true)"
STATS="$(grep -oE 'odoo\.tests\.stats: [a-z_]+: [0-9]+ tests[^ ]*' /tmp/coopeapp-test.log | sed 's/odoo\.tests\.stats: //' || true)"

if [ -z "$RES_MODULO" ] && [ -z "$RES_SUITE" ] && [ -z "$STATS" ]; then
  echo "✗ NO CORRIO NINGUN TEST."
  echo "  Odoo no imprimio ningun resumen. Un log sin tests es peor que uno en"
  echo "  rojo: parece que todo anda. Log: /tmp/coopeapp-test.log"
  grep -E '(CRITICAL|PermissionError|OperationalError)' /tmp/coopeapp-test.log | head -10
  exit 1
fi

if [ -n "$STATS" ]; then
  echo "Tests que corrieron:"
  echo "$STATS" | sed 's/^/  /'
  echo
fi

EN_ROJO=0
if [ -n "$RES_MODULO" ] && echo "$RES_MODULO" | grep -qvE ': 0 failures?, 0 errors?'; then
  EN_ROJO=1
  echo "$RES_MODULO" | grep -vE ': 0 failures?, 0 errors?' | sed 's/^/  /'
fi
if [ -n "$RES_SUITE" ] && echo "$RES_SUITE" | grep -qvE '^0 failed, 0 error'; then
  EN_ROJO=1
  echo "$RES_SUITE" | grep -vE '^0 failed, 0 error' | sed 's/^/  /'
fi

if [ "$EN_ROJO" -eq 1 ]; then
  echo
  echo "✗ HAY TESTS EN ROJO. Los que fallaron:"
  grep -E '^[0-9-]+ .*(FAIL|ERROR): ' /tmp/coopeapp-test.log \
    | sed -E 's/^.*(FAIL|ERROR): /  \1: /' | sort -u | head -30
  echo
  echo "Primer traceback (el resto en /tmp/coopeapp-test.log):"
  grep -A 18 -m 1 'Traceback (most recent call last)' /tmp/coopeapp-test.log | sed 's/^/  /'
  exit 1
fi

if [ "$RC" -ne 0 ]; then
  echo "✗ Los tests pasaron pero Odoo salio con codigo $RC. Revisa el log."
  exit "$RC"
fi

echo "✓ Todos los tests pasaron. Produccion no se toco."
