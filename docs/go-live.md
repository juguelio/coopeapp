# Go-live — poner coopeapp v1.0 en producción

Estado: v1.0 completo (M1–M7) en el repo, pero el VPS tiene una versión vieja
(solo M1/M2 deployado). Esta guía lleva el VPS a v1.0 y lo verifica. Seguir
en orden. Tiempo estimado: 30–45 min.

## 0. Antes de empezar
- [ ] `git push` (que `origin/main` tenga todo lo último).
- [ ] SSH por clave andando (`ssh coopeapp-vps 'echo ok'` no pide password).
- [ ] **Hacer un backup ANTES de tocar nada:** `ssh coopeapp-vps "cd ~/odoo-coop && ./scripts/backup-vps.sh"` (ver [runbook-backups.md](runbook-backups.md)).

## 1. Subir el código y actualizar todos los módulos (una sola vez)

`coop_ui` es nuevo (se instala con `-i`); el resto se actualiza (`-u`).
`coop_construction` ahora depende de `maintenance` — Odoo lo instala solo al
actualizar.

```bash
cd ~/Dev/coopeapp                 # en tu Mac
# subir TODOS los addons custom al VPS:
for m in coop_members coop_payroll coop_books coop_assembly coop_construction coop_portal coop_ui; do
  rsync -az --delete -e "ssh" "addons/$m" coopeapp-vps:~/odoo-coop/addons/
done

# en el VPS: instalar coop_ui + actualizar el resto, en un solo comando
ssh coopeapp-vps "cd ~/odoo-coop && \
  docker compose run --rm odoo odoo \
    -i coop_ui \
    -u coop_members,coop_payroll,coop_books,coop_assembly,coop_construction,coop_portal \
    -d coop_piloto --stop-after-init && \
  docker compose restart odoo"
```

Mirá que termine sin errores rojos. Si algo falla, el backup del paso 0 te cubre.

> Después de este primer deploy completo, los siguientes son automáticos (push a
> main) o con `./scripts/deploy.sh MODULO`.

## 2. Datos demo (SOLO si es una base de prueba)

Si `coop_piloto` ya tiene **datos reales de la cooperativa, NO corras esto.**
En una base de prueba, para ver todo cargado:
```bash
ssh coopeapp-vps "cd ~/odoo-coop && docker compose run --rm odoo odoo shell -d coop_piloto --stop-after-init < scripts/load_demo_data.py"
```
(o el comando que ya usabas para el demo).

## 3. Verificar los 4 roles en /app (con el demo: pass = <login>1234)

- [ ] **Socio** (lucas): https://www.coopeapp.com.ar/app → cargar avance (3 pasos), mi plata, obra (ve acopios), pedir material, votar, relevamiento.
- [ ] **Login PIN** (lucas, tel 2944500111, PIN 1234): https://www.coopeapp.com.ar/app/ingresar
- [ ] **Coordinador** (carlos): validar avances, pedidos, **⚡ optimizar al corralón**, herramientas.
- [ ] **Síndico** (analia): control, firmar certificado, auditoría, firmar acta.
- [ ] **Admin** (sofia): tablero, **ruta editable por oficio**, reportes filtrables.
- [ ] **PWA:** en el celular, entrar a /app → "Agregar a inicio" (Android: cartel solo; iPhone: Compartir → Agregar a inicio). Abrir el ícono → pantalla completa.
- [ ] **Offline:** activar modo avión, cargar un avance → "guardado sin señal"; volver la señal → se sincroniza.

## 4. Verificar el backoffice (/web, admin)

- [ ] Presupuesto: crear OT → memoria → presupuesto (IVA A/B) → **Imprimir PDF** → Aprobar → crea la obra.
- [ ] Acta: en una asamblea cerrada, **Generar acta** → **Imprimir acta PDF**.
- [ ] Reportes → Operaciones: pivot + **exportar a Excel**.
- [ ] El backoffice se ve **verde coopeapp** (módulo coop_ui activo).

## 5. Branding y limpieza (ver [limpieza-backoffice.md](limpieza-backoffice.md))
- [ ] Subir el **logo** de la coop: Ajustes → Compañías → logo (aparece en login y PDFs).
- [ ] **Membrete de PDFs:** Ajustes → Compañías → "Diseño del documento" → elegir layout + cargar logo. Los presupuestos y actas ya usan ese layout.
- [ ] Instalar **web_responsive** (OCA) — el salto grande de UX.
- [ ] **Desinstalar** apps Odoo que no se usen.
- [ ] Admins **sin** `base.group_system` ni modo desarrollador.

## 6. Operación continua
- [ ] **Auto-deploy:** correr `./scripts/setup-ci-deploy.sh` una vez → cada push a main deploya solo.
- [ ] **Backups:** cron diario + **probar un restore** (runbook-backups.md) ANTES de cargar datos reales.
- [ ] **PINs reales:** setear el PIN de cada socio (Ajustes → Usuarios, o un script con `user.set_coop_pin('123456')`).

## 7. Pendientes conocidos (no bloquean el piloto)
- Redirect `coopeapp.com.ar` pelado → `/app` (hoy hay que dar el link con /app). Toca el root, hacerlo con prueba en mano.
- v1.1: audio→transcripción de asamblea, import de listas de precio desde PDF, alertas de precio viejo.
- El branding por CSS de coop_ui es best-effort: revisar en pantalla y ajustar selectores si algo quedó raro.
