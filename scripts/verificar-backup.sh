#!/usr/bin/env bash
# Verifica que el backup de coopeapp sirva de verdad. Corre EN EL VPS.
#
# Por qué existe, y por qué no alcanza con `backup.sh`:
#
# `backup.sh` detecta lo que falla MIENTRAS corre. No detecta que no haya
# corrido —cron apagado, el script borrado, el VPS caído— ni que el dump que
# escribió no se pueda restaurar. Un `pg_dump` puede terminar en 0 y dejar un
# archivo que `pg_restore` no lee.
#
# Hace tres cosas, de menor a mayor costo:
#
#   1. FRESCURA   el dump más nuevo es de hoy y no está vacío.
#   2. LEGIBLE    `pg_restore -l` lo lee y lista tablas con datos.
#   3. RESTORE    lo restaura de verdad en una base descartable y cuenta filas
#                 en las tablas que importan. Solo con --restore, porque tarda
#                 y carga el Postgres que sirve producción.
#
# El paso 3 es el único que prueba lo que el backup promete. Los otros dos son
# baratos y se pueden correr todos los días.
#
# Uso:
#   ./verificar-backup.sh              → frescura + legibilidad (segundos)
#   ./verificar-backup.sh --restore    → además restaura y cuenta filas
#
# Salida distinta de 0 = hay que mirar. Pensado para que cron mande mail.
set -uo pipefail

# Sobreescribible para poder probar que este script sabe FALLAR, sin tocar los
# backups de verdad. Un verificador que nunca se probó en rojo es un cartel de
# "todo bien" colgado en la pared.
BACKUP_DIR="${BACKUP_DIR:-$HOME/odoo-coop/backups}"
DB_CONTAINER="odoo-coop-db"
DB_PROD="coop_piloto"
DB_VERIF="coop_verif_restore"
MAX_HORAS="${MAX_HORAS:-30}"   # 30 y no 24: el cron corre 03:00, damos aire
RESTORE=0
[ "${1:-}" = "--restore" ] && RESTORE=1

fallo() { echo "[ALERT][verificar-backup] $*"; exit 1; }

if [ "$DB_VERIF" = "$DB_PROD" ]; then
  fallo "la base de verificación no puede ser producción."
fi

# ── 1. frescura ──────────────────────────────────────────────────────────────
DUMP="$(ls -t "$BACKUP_DIR"/db_${DB_PROD}_*.dump 2>/dev/null | head -1)"
[ -n "$DUMP" ] || fallo "no hay NINGÚN dump en $BACKUP_DIR."
[ -s "$DUMP" ] || fallo "el dump más nuevo está VACÍO: $DUMP"

AHORA=$(date +%s)
MTIME=$(stat -c %Y "$DUMP")
HORAS=$(( (AHORA - MTIME) / 3600 ))
BYTES=$(stat -c %s "$DUMP")
echo "dump más nuevo: $(basename "$DUMP")"
echo "  edad: ${HORAS}h · tamaño: ${BYTES} bytes"

if [ "$HORAS" -gt "$MAX_HORAS" ]; then
  fallo "el backup más nuevo tiene ${HORAS}h (máximo ${MAX_HORAS}h). El cron no corrió."
fi

# Un dump que de golpe pesa una fracción del anterior es una señal: la base no
# se encoge sola. Se compara contra el anterior, no contra un número fijo.
ANTERIOR="$(ls -t "$BACKUP_DIR"/db_${DB_PROD}_*.dump 2>/dev/null | sed -n 2p)"
if [ -n "$ANTERIOR" ] && [ -s "$ANTERIOR" ]; then
  BYTES_ANT=$(stat -c %s "$ANTERIOR")
  MINIMO=$(( BYTES_ANT / 2 ))
  if [ "$BYTES" -lt "$MINIMO" ]; then
    fallo "el dump de hoy (${BYTES}) pesa menos de la mitad que el anterior (${BYTES_ANT}). Revisalo antes de confiar en él."
  fi
fi

# ── 2. legibilidad ───────────────────────────────────────────────────────────
TABLAS="$(docker exec -i "$DB_CONTAINER" pg_restore -l < "$DUMP" 2>/dev/null | grep -c 'TABLE DATA')"
if [ -z "$TABLAS" ] || [ "$TABLAS" -lt 100 ]; then
  fallo "pg_restore solo pudo leer ${TABLAS:-0} tablas con datos. El dump está corrupto o truncado."
fi
echo "  legible: $TABLAS tablas con datos"

if [ "$RESTORE" -eq 0 ]; then
  echo "✓ Backup fresco y legible. (Para probar el restore de verdad: --restore)"
  exit 0
fi

# ── 3. restore de verdad ─────────────────────────────────────────────────────
# Se restaura en una base aparte. `coop_piloto` no se toca en ningún paso.
echo "→ Restaurando en '$DB_VERIF' (producción no se toca)..."
docker exec "$DB_CONTAINER" psql -U odoo -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_VERIF'" >/dev/null 2>&1
docker exec "$DB_CONTAINER" dropdb -U odoo --if-exists "$DB_VERIF" || true
docker exec "$DB_CONTAINER" createdb -U odoo -O odoo "$DB_VERIF" \
  || fallo "no se pudo crear la base de verificación."

if ! docker exec -i "$DB_CONTAINER" pg_restore -U odoo -d "$DB_VERIF" --no-owner < "$DUMP" 2>/tmp/verif-restore.err; then
  # pg_restore avisa de cosas menores con exit 1; lo que decide es si los datos
  # llegaron, y eso se mide abajo contando filas. Se deja el error a la vista.
  echo "  (pg_restore terminó con avisos:)"
  tail -5 /tmp/verif-restore.err | sed 's/^/    /'
fi

# Las tablas que importan: si el restore trajo el esquema pero no las filas, un
# `count(*)` de tablas del negocio lo desnuda. Un dump vacío pasa el paso 2 y
# muere acá.
PROBLEMAS=0
for T in coop_member coop_foja_item coop_avance_medicion coop_assembly res_users; do
  N_PROD=$(docker exec "$DB_CONTAINER" psql -U odoo -d "$DB_PROD" -t -c "SELECT count(*) FROM $T" 2>/dev/null | tr -d ' \n')
  N_VER=$(docker exec "$DB_CONTAINER" psql -U odoo -d "$DB_VERIF" -t -c "SELECT count(*) FROM $T" 2>/dev/null | tr -d ' \n')
  if [ -z "$N_VER" ]; then
    echo "  ✗ $T: no existe en el restore"; PROBLEMAS=$((PROBLEMAS + 1)); continue
  fi
  # El restore es de las 03:00 y producción sigue viva, así que puede tener
  # MENOS filas que ahora. Lo que no puede es tener cero donde producción tiene.
  if [ "$N_PROD" -gt 0 ] && [ "$N_VER" -eq 0 ]; then
    echo "  ✗ $T: producción tiene $N_PROD filas y el restore 0"; PROBLEMAS=$((PROBLEMAS + 1))
  else
    echo "  ✓ $T: $N_VER filas restauradas (producción tiene $N_PROD)"
  fi
done

echo "→ Borrando la base de verificación..."
docker exec "$DB_CONTAINER" psql -U odoo -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_VERIF'" >/dev/null 2>&1
docker exec "$DB_CONTAINER" dropdb -U odoo --if-exists "$DB_VERIF" || true

[ "$PROBLEMAS" -eq 0 ] || fallo "$PROBLEMAS tabla(s) no se restauraron. El backup NO sirve."
echo "✓ El backup se restaura y trae los datos. Producción no se tocó."
