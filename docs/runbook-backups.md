# Runbook — Backups del VPS (coopeapp)

**Objetivo:** que nunca se pierdan los datos de la cooperativa piloto (nómina,
avances, actas). Un backup sin restore probado NO es backup.

> Verificado contra el VPS el **2026-07-28**. Lo que sigue es lo que realmente
> corre, no lo que se planeó.

## Qué se respalda

- **Base de datos** `coop_piloto` (dump `pg_dump -Fc`): todo Odoo.
- **Filestore**: adjuntos (PDFs de actas/certificados, fotos).

## Lo que realmente corre hoy

```txt
script   ~/odoo-coop/backup.sh          (EN EL VPS)
cron     0 3 * * *  →  todos los días a las 03:00
log      ~/odoo-coop/backups/backup.log
destino  ~/odoo-coop/backups/
nombres  db_coop_piloto_AAAA-MM-DD_HHMMSS.dump
         filestore_AAAA-MM-DD_HHMMSS.tar.gz
retención 14 días
volumen  ~5,1 MB el dump + ~4,3 MB el filestore por día (~144 MB en total)
```

Estado verificado el 2026-07-28: **12 dumps + 12 filestore, sin huecos**, el más
reciente de ese mismo día 03:00.

> ⚠️ **Deuda 1 — el script que corre no está versionado.** `~/odoo-coop/backup.sh`
> vive solo en el VPS. Si se pierde el server, se pierde también el script que
> hacía los backups. `scripts/backup-vps.sh` (en este repo) es una versión
> **anterior y distinta** — otro destino (`~/backups/`), otros nombres de archivo
> y retención de 30 días — que **no es la que está en cron**. No la uses como
> referencia: ignorala o alineala antes de tocar nada.
>
> ⚠️ **Deuda 2 — no hay copia offsite.** Ver la sección de abajo. Es lo que falta
> para que esto sea un backup de verdad y no una copia local.

## Copia offsite — PENDIENTE (bloqueante para datos reales)

Hoy los 24 archivos viven en el **mismo VPS** cuya base respaldan. Un incidente
del server (disco, borrado, baja del proveedor) se lleva la nómina, las actas y
los certificados firmados de una cooperativa real, junto con sus backups.

Configurar una vez, en el VPS:

```bash
ssh coopeapp-vps
rclone config          # crear un remoto "b2" (Backblaze B2: gratis hasta 10 GB)
```

Y agregar al final de `~/odoo-coop/backup.sh`, **antes** del `echo` final:

```bash
rclone copy "$BACKUP_DIR/db_${DB_NAME}_${DATE}.dump" b2:coopeapp-backups/ || true
rclone copy "$BACKUP_DIR/filestore_${DATE}.tar.gz"   b2:coopeapp-backups/ || true
```

Check externo de que anda (no alcanza con "lo configuré"):

```bash
rclone ls b2:coopeapp-backups/ | tail -3     # tiene que aparecer el dump de hoy
```

## Restore — PROBADO ✅

**Último restore probado: 2026-07-28** — dump `db_coop_piloto_2026-07-28_030001.dump`
restaurado a una base aislada. `pg_restore` terminó con **exit 0 y stderr vacío**;
se compararon 8 tablas contra producción y las únicas diferencias fueron dos
escrituras hechas *después* del dump. Base de prueba borrada al terminar;
`coop_piloto` nunca se tocó. Evidencia:
`obsidian-vault/03-Hermes/generated/2026-07-28-coopeapp-pilot-activation-result.md`.

Comandos exactos, tal como se ejecutaron:

```bash
ssh coopeapp-vps
DUMP=~/odoo-coop/backups/db_coop_piloto_AAAA-MM-DD_HHMMSS.dump

# 1. base de prueba nueva y aislada (NUNCA restaurar sobre coop_piloto)
docker exec odoo-coop-db createdb -U odoo -O odoo coop_restore_test

# 2. restaurar el dump ahí
docker exec -i odoo-coop-db pg_restore -U odoo -d coop_restore_test \
    --no-owner --no-acl < "$DUMP"
# esperado: exit 0 y stderr vacío

# 3. verificar que trajo datos (comparar contra prod)
for T in res_users res_partner coop_member project_project \
         coop_avance_medicion coop_certificado coop_assembly; do
  P=$(docker exec odoo-coop-db psql -U odoo -d coop_piloto      -tAc "SELECT count(*) FROM $T")
  R=$(docker exec odoo-coop-db psql -U odoo -d coop_restore_test -tAc "SELECT count(*) FROM $T")
  printf "%-24s prod=%-6s restore=%-6s\n" "$T" "$P" "$R"
done

# 4. filestore, solo si vas a abrir la copia con Odoo
docker exec odoo-coop-app mkdir -p /var/lib/odoo/filestore/coop_restore_test
tar xzf ~/odoo-coop/backups/filestore_AAAA-MM-DD_HHMMSS.tar.gz -C /tmp/fsrestore
docker cp /tmp/fsrestore/filestore/coop_piloto/. \
    odoo-coop-app:/var/lib/odoo/filestore/coop_restore_test/

# 5. BORRAR la base de prueba al terminar (no dejarla viva)
docker exec odoo-coop-db dropdb -U odoo coop_restore_test
docker exec odoo-coop-db psql -U odoo -d postgres -tAc \
    "SELECT datname FROM pg_database WHERE datistemplate=false"
```

> Nota sobre el nombre del contenedor: son `odoo-coop-db` (Postgres) y
> `odoo-coop-app` (Odoo). El tarball del filestore empaqueta todo `odoo-data`,
> así que adentro la ruta es `./filestore/coop_piloto/…`.

### Para qué sirve además la base de prueba

Es el lugar correcto para ensayar `scripts/purge_demo.py` antes del go-live —
que a la fecha **nunca corrió en real**. Restaurás, corrés el purge sobre la
copia, mirás qué borra y qué queda, y recién ahí lo hacés en serio.
Ver `docs/go-live-datos.md`.

## Checklist pre-piloto

- [x] `backup.sh` corre sin errores (12 días corridos verificados).
- [x] Cron diario configurado (`0 3 * * *`).
- [x] **Restore probado end-to-end** (2026-07-28).
- [ ] **Copia offsite (rclone) configurada** ← lo único que falta.
- [ ] Script de backup versionado en el repo.
