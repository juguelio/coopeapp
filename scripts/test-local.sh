#!/usr/bin/env bash
# Odoo + PostgreSQL aislados; nunca conecta al VPS ni a coop_piloto.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
COMPOSE=(docker compose --env-file /dev/null -f scripts/compose.pilot-test.yml)
MODULES=coop_members,coop_payroll,coop_assembly,coop_books,coop_construction,coop_portal,coop_ui
TAGS=/coop_members,/coop_payroll,/coop_assembly,/coop_books,/coop_construction,/coop_portal,/coop_ui
LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/coopeapp-tests.XXXXXX")"
echo "Logs: $LOG_DIR"

# Proyecto separado del entorno manual de piloto: permite correr ambos sin
# borrar fixtures ni detener el servidor que usa el navegador.
COMPOSE+=(-p coopeapp-regression)
cleanup() { "${COMPOSE[@]}" down --volumes > "$LOG_DIR/cleanup.log" 2>&1; }
trap cleanup EXIT
"${COMPOSE[@]}" up -d db
python3 scripts/check-xml-order.py
python3 -m unittest discover -s scripts/tests -v
node addons/coop_portal/tests/test_pwa_worker.cjs
node addons/coop_portal/tests/test_pwa_queue.cjs
"${COMPOSE[@]}" run --rm -T odoo python3 -m unittest discover \
  -s /mnt/extra-addons/coop_construction/tests -p test_foja_parser.py -v
"${COMPOSE[@]}" run --rm -T odoo odoo -d coop_pilot_local_test \
  -i "$MODULES" --without-demo=all --workers=0 --max-cron-threads=0 \
  --stop-after-init > "$LOG_DIR/install.log" 2>&1 || {
    tail -80 "$LOG_DIR/install.log"; exit 1;
  }
"${COMPOSE[@]}" run --rm -T odoo odoo -d coop_pilot_local_test \
  -u "$MODULES" --test-enable --test-tags "$TAGS" \
  --db-filter '^coop_pilot_local_test$' --workers=0 --max-cron-threads=0 \
  --stop-after-init --log-level=test > "$LOG_DIR/tests.log" 2>&1 || {
    tail -100 "$LOG_DIR/tests.log"; exit 1;
  }
# Un proceso que termina en 0 sin descubrir tests no prueba nada.
docker run --rm -v "$LOG_DIR:/logs:ro" --entrypoint python3 odoo:18.0 -c '
import pathlib, re, sys
text = pathlib.Path("/logs/tests.log").read_text()
results = re.findall(r"(\d+) failed, (\d+) error\(s\) of (\d+) tests", text)
for failed, errors, count in results:
    print(f"{failed} fallas, {errors} errores, {count} tests")
sys.exit(0 if results and all(int(f) == int(e) == 0 for f,e,n in results)
         and sum(int(n) for f,e,n in results) > 0 else 1)
'
