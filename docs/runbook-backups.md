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

> ✅ **Deuda 1 (script sin versionar) — SALDADA 2026-07-29.** `scripts/backup-vps.sh`
> en este repo **es** el script que corre. Si lo editás, subilo:
> `scp scripts/backup-vps.sh coopeapp-vps:~/odoo-coop/backup.sh`.
> La versión anterior del VPS quedó guardada como `backup.sh.bak-2026-07-29`.

## Copia offsite — ✅ ACTIVA (2026-07-29)

Backblaze B2, bucket **privado** `coopeapp-backups`, remoto rclone `b2remote`.
La app key está restringida a ese bucket (no es la master key) y vive solo en
`~/.config/rclone/rclone.conf` del VPS, con permisos 600.

`rclone` está instalado como binario de usuario en `~/bin/rclone` (el VPS no
tiene sudo sin password). **El script lo llama por ruta absoluta a propósito:**
cron corre con un PATH mínimo que no incluye `~/bin`, así que un `rclone` pelado
fallaría en silencio todas las noches.

> ⚠️ **Nada de `|| true` en la subida.** Una versión previa de este runbook lo
> sugería y estaba mal: se traga el error y el backup termina diciendo "OK" sin
> haber copiado nada. Es el mismo modo de falla que tuvo el auto-deploy del CI
> durante 3 pushes. Si la copia offsite falla, el script corta con
> `[ALERT][backup]` y sale con código 1.

Retención: **14 días en local, sin límite en offsite**. Es deliberado — el objeto
de la copia remota es sobrevivir a un borrado accidental de este server,
incluido uno hecho por este mismo script. A ~10 MB/día entran años en los 10 GB
gratis de B2.

### Verificar que sigue viva (check externo, no la palabra del script)

```bash
ssh coopeapp-vps
~/bin/rclone ls b2remote:coopeapp-backups/ | tail -4   # tiene que estar el dump de hoy
~/bin/rclone size b2remote:coopeapp-backups/
grep '\[ALERT\]' ~/odoo-coop/backups/backup.log        # vacío = ninguna noche falló
```

La prueba dura es bajar el dump **remoto** y confirmar que se puede leer:

```bash
~/bin/rclone copy b2remote:coopeapp-backups/db_coop_piloto_AAAA-MM-DD_HHMMSS.dump /tmp/verif/
docker exec -i odoo-coop-db pg_restore -l < /tmp/verif/db_coop_piloto_*.dump | grep -c '^[0-9]'
rm -rf /tmp/verif
```

Verificado el 2026-07-29: checksums local↔remoto sin diferencias, y el dump
bajado de B2 devuelve **9312 objetos** legibles por `pg_restore`. Los dos caminos
de error probados a mano (remoto inexistente, `rclone` ausente) cortan con
`[ALERT]` y exit 1 en vez de reportar éxito. Cobertura inicial subida de una:
**15 días** (2026-07-15 → 2026-07-29), 167 MB.

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
- [x] **Copia offsite configurada y verificada** (2026-07-29, B2).
- [x] Script de backup versionado en el repo (`scripts/backup-vps.sh`).
- [x] El script falla ruidosamente en vez de reportar éxito falso.

Con esto los backups dejan de ser el bloqueante para cargar datos reales.

## Lo que sigue sin cubrir (asumido, no olvidado)

- **Nadie avisa si el cron deja de correr.** Si el server se apaga o el cron
  muere, no hay backup y tampoco hay alerta: el log simplemente deja de crecer.
  Un chequeo semanal a mano (`rclone ls` + fecha del último dump) alcanza para el
  piloto; si la coop se vuelve crítica, conviene un dead-man's switch.
- **La app key vive solo en el VPS.** Si se pierde el server hay que generar una
  nueva en Backblaze para bajar los backups — no es un bloqueo (los datos están
  en B2 y se accede desde la consola web), pero conviene tener el par guardado
  también en el vault.

---

## Correr los tests sin tocar producción (2026-08-24)

`docker compose` **no existe en la Mac**: el compose vive en el VPS
(`~/odoo-coop`). Y correr los tests con `-u ... -d coop_piloto` **es correrlos
contra producción** — el `-u` la actualiza de verdad.

```bash
./scripts/test-vps.sh                      # los tres módulos
./scripts/test-vps.sh coop_assembly        # uno solo
```

El script sube los addons a `~/odoo-coop/addons-test/` (un directorio aparte,
no pisa los de producción), lee el `addons_path` real del contenedor en vez de
inventarlo, crea una base descartable `coop_test_ci`, instala ahí con
`--test-enable --without-demo=all`, y borra la base al terminar.
`coop_piloto` no se toca en ningún paso.

Si no puede leer el `addons_path` **para** en vez de seguir: unos tests que
"pasan" porque Odoo no encontró los módulos son peores que unos tests en rojo.

### Los tests del parser de cómputos corren sin Odoo

`foja_parser.py` no importa Odoo a propósito, así que sus tests corren en
cualquier lado con Python y `openpyxl`:

```bash
python3 addons/coop_construction/tests/test_foja_parser.py
```
