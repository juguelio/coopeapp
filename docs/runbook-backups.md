# Runbook — Backups del VPS (coopeapp)

**Objetivo:** que nunca se pierdan los datos de la cooperativa piloto (nómina,
avances, actas). Un backup sin restore probado NO es backup.

## Qué se respalda
- **Base de datos** `coop_piloto` (dump `pg_dump -Fc`): todo Odoo.
- **Filestore**: adjuntos (PDFs de actas/certificados, fotos).

## Setup (una vez, en el VPS)

```bash
ssh coopeapp-vps          # alias configurado por scripts/setup-ssh.sh
cd ~/odoo-coop
mkdir -p ~/backups
# probar el script a mano:
./scripts/backup-vps.sh
ls -lh ~/backups
```

Si el dump y el `filestore-*.tar.gz` aparecen con tamaño > 0, anda.
Si el filestore falla, ajustá `DB_SERVICE`/la ruta del filestore en el script
(según cómo esté montado el volumen en tu `docker-compose.yml`).

## Programar (cron diario 3:15 AM)

```bash
crontab -e
# agregar:
15 3 * * * /home/odoo-admin/odoo-coop/scripts/backup-vps.sh >> /home/odoo-admin/backups/backup.log 2>&1
```

## Copia offsite (recomendado)

Un backup en el mismo server no protege contra perder el server. Configurá
`rclone` a Backblaze B2 / S3 (gratis hasta 10GB en B2):

```bash
rclone config            # crear remoto "b2"
# luego descomentar las líneas "rclone copy" en scripts/backup-vps.sh
```

## Restore (PROBARLO, no es opcional)

```bash
ssh coopeapp-vps
cd ~/odoo-coop
# 1. crear una DB de prueba y restaurar el dump ahí:
docker compose exec -T db createdb -U odoo coop_restore_test
docker compose exec -T db pg_restore -U odoo -d coop_restore_test \
    < ~/backups/coop_piloto-AAAAMMDD-HHMM.dump
# 2. restaurar el filestore en la DB de prueba:
docker compose exec -T odoo mkdir -p /var/lib/odoo/filestore/coop_restore_test
tar xzf ~/backups/filestore-coop_piloto-AAAAMMDD-HHMM.tar.gz -C /tmp
docker compose cp /tmp/coop_piloto/. odoo:/var/lib/odoo/filestore/coop_restore_test/
# 3. levantar Odoo apuntando a coop_restore_test y verificar que abre y tiene datos.
# 4. borrar la DB de prueba cuando confirmes:
docker compose exec -T db dropdb -U odoo coop_restore_test
```

**Documentá la fecha del último restore probado acá:**
- Último restore probado: _(pendiente — probar antes de cargar datos reales)_

## Checklist pre-piloto
- [ ] `backup-vps.sh` corre a mano sin errores.
- [ ] Cron diario configurado.
- [ ] Copia offsite (rclone) configurada.
- [ ] **Restore probado** end-to-end al menos una vez.
