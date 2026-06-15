#!/usr/bin/env bash
# Backup diario de coopeapp en el VPS: dump de la DB + filestore, con retención.
# Pensado para correr por cron EN EL VPS (no desde la Mac).
#   crontab -e  →  15 3 * * *  /home/odoo-admin/odoo-coop/scripts/backup-vps.sh >> /home/odoo-admin/backups/backup.log 2>&1
#
# Requiere: docker compose corriendo en ~/odoo-coop. Ajustá DB/SERVICE si difieren.
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-$HOME/odoo-coop}"
DB="${DB:-coop_piloto}"
DB_SERVICE="${DB_SERVICE:-db}"        # nombre del servicio Postgres en docker compose
DB_USER="${DB_USER:-odoo}"
DEST="${DEST:-$HOME/backups}"
RETENCION_DIAS="${RETENCION_DIAS:-30}"
FECHA="$(date +%Y%m%d-%H%M)"

mkdir -p "$DEST"
cd "$COMPOSE_DIR"

echo "→ [$FECHA] Dump de la base $DB..."
docker compose exec -T "$DB_SERVICE" pg_dump -U "$DB_USER" -Fc "$DB" \
  > "$DEST/${DB}-${FECHA}.dump"

echo "→ Backup del filestore..."
# El filestore vive dentro del contenedor de Odoo en ~/.local/share/Odoo/filestore/<DB>.
# Lo copiamos a un tar. Si usás un volumen/bind distinto, ajustá la ruta.
docker compose exec -T odoo tar czf - -C /var/lib/odoo/filestore "$DB" \
  > "$DEST/filestore-${DB}-${FECHA}.tar.gz" 2>/dev/null \
  || echo "  (aviso: revisá la ruta del filestore si esto falló)"

echo "→ Retención: borro backups de más de $RETENCION_DIAS días..."
find "$DEST" -name "${DB}-*.dump" -mtime "+$RETENCION_DIAS" -delete
find "$DEST" -name "filestore-${DB}-*.tar.gz" -mtime "+$RETENCION_DIAS" -delete

# ── Copia offsite (descomentá y configurá rclone una vez: rclone config) ──
# rclone copy "$DEST/${DB}-${FECHA}.dump" "b2:coopeapp-backups/" 2>/dev/null || true
# rclone copy "$DEST/filestore-${DB}-${FECHA}.tar.gz" "b2:coopeapp-backups/" 2>/dev/null || true

echo "✓ Backup completo: $DEST/${DB}-${FECHA}.dump"
