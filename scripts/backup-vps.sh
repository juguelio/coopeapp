#!/bin/bash
# Backup diario de coopeapp: dump de la DB + filestore, copia offsite y retención.
#
# ESTE es el script que corre en el VPS. Vive en ~/odoo-coop/backup.sh y se
# dispara por cron:
#     0 3 * * *  /home/odoo-admin/odoo-coop/backup.sh >> /home/odoo-admin/odoo-coop/backups/backup.log 2>&1
# Si lo editás acá, subilo:  scp scripts/backup-vps.sh coopeapp-vps:~/odoo-coop/backup.sh
#
# Regla de oro: este script NUNCA puede terminar diciendo "OK" si algo falló.
# Un backup que reporta éxito sin haber respaldado es peor que uno que revienta,
# porque nadie vuelve a mirarlo.
set -uo pipefail

BACKUP_DIR="$HOME/odoo-coop/backups"
DATE=$(date +%Y-%m-%d_%H%M%S)
DB_NAME="coop_piloto"
DB_CONTAINER="odoo-coop-db"
# Ruta absoluta a propósito: cron corre con un PATH mínimo y ~/bin no está en
# él, así que un `rclone` pelado acá fallaría en silencio todas las noches.
RCLONE="$HOME/bin/rclone"
REMOTO="b2remote:coopeapp-backups"

DUMP="$BACKUP_DIR/db_${DB_NAME}_${DATE}.dump"
FILESTORE="$BACKUP_DIR/filestore_${DATE}.tar.gz"

fallo() {
    # Prefijo grepeable para revisar el log de un vistazo:
    #   grep '\[ALERT\]' ~/odoo-coop/backups/backup.log
    echo "[ALERT][backup][$DATE] $*"
    exit 1
}

mkdir -p "$BACKUP_DIR"

# ── Base de datos ────────────────────────────────────────────────────────────
# La redirección crea el archivo aunque pg_dump falle, así que no alcanza con
# mirar que exista: hay que chequear el código de salida Y que no esté vacío.
docker exec "$DB_CONTAINER" pg_dump -U odoo -Fc "$DB_NAME" > "$DUMP" \
    || fallo "pg_dump falló para $DB_NAME"
[ -s "$DUMP" ] || fallo "el dump quedó vacío: $DUMP"

# ── Filestore (adjuntos: actas, certificados, fotos) ─────────────────────────
tar czf "$FILESTORE" -C "$HOME/odoo-coop/odoo-data" . 2>/dev/null
[ -s "$FILESTORE" ] || fallo "el filestore quedó vacío: $FILESTORE"

# ── Copia offsite ────────────────────────────────────────────────────────────
# Sin esto los backups viven en el mismo server cuya base respaldan, y un
# incidente del VPS se lleva los datos y las copias en el mismo movimiento.
# Por eso va SIN "|| true": si la subida falla, el backup del día no está
# completo y tiene que gritar.
[ -x "$RCLONE" ] || fallo "no encuentro $RCLONE — la copia offsite no corrió"
"$RCLONE" copy "$DUMP" "$REMOTO/" \
    || fallo "rclone no pudo subir el dump a $REMOTO"
"$RCLONE" copy "$FILESTORE" "$REMOTO/" \
    || fallo "rclone no pudo subir el filestore a $REMOTO"

# ── Retención ────────────────────────────────────────────────────────────────
# Solo LOCAL. Lo offsite se acumula a propósito: es la copia que tiene que
# sobrevivir a un borrado accidental de este server, incluido uno hecho por
# este mismo script. A ~10 MB/día entran años en el tier gratis de B2.
find "$BACKUP_DIR" -name "db_*.dump"          -mtime +14 -delete
find "$BACKUP_DIR" -name "filestore_*.tar.gz" -mtime +14 -delete

echo "Backup OK: $DATE (local + offsite en $REMOTO)"
