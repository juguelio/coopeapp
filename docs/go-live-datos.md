# Transición demo → producción (datos reales del piloto)

Cómo pasar la base `coop_piloto` de los datos de demostración a los datos reales
de la primera cooperativa, sin romper nada.

## Qué hay hoy y qué queremos

- Hoy `coop_piloto` (en prod, `https://coopeapp.com.ar`) tiene **datos demo**
  (socios lucas/carlos/sofia/analia, obra "San Martín de los Andes", materiales
  y corralones de prueba), cargados con `scripts/load_demo_data.py`.
- Queremos dejar la base **limpia** y cargar la cooperativa real.

## Decisión: purga en la misma base (recomendado)

El demo está **etiquetado** (email `@demo.coop`, logins conocidos, nombres de
obra/materiales). Hay un script de purga (`scripts/purge_demo.py`) que
borra **solo lo demo** y deja intacta la configuración, los módulos y cualquier
dato real. Es lo más rápido y seguro para el piloto.

> ⚠️ El script **nunca se corrió en real**: antes del día D, restaurar el backup
> en una base staging y correrlo ahí (de paso valida el restore). El script
> ABORTA solo si detecta socios reales cargados (guarda anti-arrasamiento) y
> termina con `PURGA INCOMPLETA` visible si algún borrado falló.

> Alternativa "base nueva de cero" (máxima limpieza, numeración desde 1): recrear
> `coop_piloto` con `-i ... --without-demo=all`. Más prolijo pero hay que volver a
> configurar empresa/logo/membrete. Solo vale si te molesta que la numeración de
> OT/certificados arranque en 2-3 en vez de 1. Para el piloto, **no hace falta**.

---

## Paso a paso

### 1. Backup ANTES de tocar nada
```bash
ssh coopeapp-vps "cd ~/odoo-coop && docker compose exec -T db pg_dump -U odoo coop_piloto | gzip > ~/backup_pre_golive_$(date +%F).sql.gz && ls -lh ~/backup_pre_golive_*.sql.gz"
```
Guardá ese archivo. Si algo sale mal, se restaura con `gunzip -c ... | docker compose exec -T db psql -U odoo coop_piloto`.

### 2. Purgar el demo

> 🔴 **Ensayalo primero en una copia.** Restaurá el último dump a
> `coop_restore_test` (comandos en `docs/runbook-backups.md`) y corré el purge
> **ahí**. Recién cuando veas que borra lo que tiene que borrar, corrélo en
> serio. El script todavía no corrió nunca sobre datos reales.

```bash
cd ~/Dev/coopeapp
rsync -az -e ssh scripts/purge_demo.py coopeapp-vps:~/odoo-coop/scripts/
ssh coopeapp-vps "cd ~/odoo-coop && cat scripts/purge_demo.py | docker compose run --rm -T odoo odoo shell -d coop_piloto"
```

Imprime qué borró y termina en `PURGA COMPLETA` o en `PURGA INCOMPLETA` con el
detalle. Si quedó algún `(aviso)`, revisalo a mano (suele ser un FK; rara vez
pasa).

#### Si aborta con "hay N socio(s) NO-demo"

Es la guarda anti-arrasamiento haciendo su trabajo: el script matchea catálogos
por nombre y se niega a correr si detecta socios que no están etiquetados como
demo. **Ahora lista cuáles son**, con id, nombre y email.

Ojo con lo que significa: un socio cargado **a mano** durante las pruebas (sin
email `@demo.coop`) cuenta como "no-demo" y bloquea la purga, aunque sea basura
de test. Verificado el 2026-07-28 en `coop_piloto`: hay un `coop.member id=1`
llamado "Juan" sin email que **hoy aborta el script**. Hay que decidirlo antes
del día D, no ese día.

Decisión por cada socio que aparezca en la lista:
- **es resto de pruebas** → borralo a mano en /web y volvé a correr el purge;
- **es un socio real ya cargado** → NO corras este script.

#### Si aborta con "hay N obra(s) que la purga no reconoce como demo"

El script solo borra lo **etiquetado** como demo (email `@demo.coop`, logins
`carlos/lucas/sofia/analia`, obra "Obra Piloto San Martín de los Andes",
catálogos por nombre). Una obra creada a mano desde la app durante las pruebas no
lleva marcador, y **no es un resto inofensivo**: sus hijos (órdenes al corralón,
pedidos) apuntan con FK `restrict` a los materiales y corralones demo, así que
impiden borrarlos y la purga muere a mitad de camino dejando la base **medio
limpia** — el peor estado posible. Por eso el script corta antes de tocar nada.

Caso conocido a 2026-07-28 en `coop_piloto`: la obra **archivada**
`project.project id=1 "Obra Piloto Sm Andes"`, con 2 órdenes de corralón y 3
pedidos colgando, creada a mano y con un botón de WhatsApp que apunta a un
corralón de prueba. Archivarla la sacó del tablero pero no de la base.

#### Secuencia de destrabe (probada sobre una copia el 2026-07-28)

En este orden — está encadenado, y al revés no funciona: el socio "Juan" es
`capataz_id` **y** `director_id` de la obra fantasma, así que no se puede borrar
antes que ella.

```txt
1. borrar la obra sin marcador CON todo su árbol de hijos
   (orden.corralon → pedido.material → avance.medicion → foja.item →
    etapa → certificado → work.entry → nota → project.task → la obra)
2. borrar el/los socio(s) que nombró la primera guarda
3. correr purge_demo.py  →  PURGA COMPLETA en una sola pasada
```

Verificado end-to-end sobre `coop_restore_test`: con esa secuencia el script
termina en `PURGA COMPLETA` **sin un solo aviso**, y la copia queda con 0
partners demo, 0 socios, 0 obras, 0 materiales y 0 corralones. Sin el paso 1, la
misma corrida termina en `PURGA INCOMPLETA` con materiales, corralones, socios y
contactos demo sobrevivientes.

### 3. Configurar la cooperativa (una vez, en /web)
Entrá al escritorio (`coopeapp.com.ar/web/login`, usuario admin) y cargá:
- **Ajustes → Compañías**: razón social, CUIT, dirección, **logo** (aparece en el
  login y en los PDF).
- **Ajustes → Usuarios y compañías → Document layout**: membrete para los PDF
  (presupuestos, certificados).
- Confirmá la **moneda** (ARS) y, si usás, los datos de IVA.

### 4. Cargar los catálogos (en /web → Construcción)
En este orden, porque después se usan:
- **Materiales → Catálogo de Materiales**: lo que los socios van a poder pedir.
- **Configuración → Unidades de Producción**: ítems con precio de referencia.
- **Materiales → Corralones**: nombre + **WhatsApp** (con código de país, ej.
  `5492944xxxxxx`) de cada proveedor.
- **Materiales → Precios Actuales** y **Acopios** (si la coop ya tiene acopios):
  esto alimenta al **optimizador de compras**.

### 5. Cargar el padrón de socios (en /web → Cooperativa → Socios)
Por cada socio real: **nombre, DNI, CUIL, teléfono, rol**. Al guardar:
- Se crea **solo** su acceso a la app (usuario = DNI, **PIN = últimos 4 del DNI**).
- Tocá **Aprobar** para dejarlo Activo.

> El teléfono tiene que ser el real del socio (es con el que entra a la app).

### 6. Crear la(s) obra(s)
Dos caminos:
- **Por el pipeline (recomendado):** App del admin → Nuevo trabajo → mandar a
  medir → validar relevamiento → en /web armar el **presupuesto** → **Aprobar**
  (crea la obra + etapas solo).
- **Directo en /web → Construcción → Obras:** cargar la obra, el monto, el
  comitente.

En la obra, cargá:
- **Foja de Medición** (los ítems con cantidad, precio, unidad) — **sin foja los
  socios no pueden cargar avances**.
- **Plantel** (los socios) y el **capataz** (que será el coordinador en la app).
- **Tareas + dependencias** (Hoja de Ruta) si querés la ruta crítica visual, y
  tocá **Calcular ruta crítica**.

### 7. Onboarding de la gente
- A cada socio: pasale el enlace `coopeapp.com.ar/app/ingresar`, su **teléfono** y
  su **PIN** (últimos 4 del DNI), y ayudalo a **instalar la app** (Agregar a
  pantalla de inicio) y a **cambiar el PIN** la primera vez.
- Verificá que el capataz vea sus bandejas (Validar/Pedidos/Corralón/Avance) y el
  síndico su Control/Firmar.

### 8. Smoke test final
- Socio: cargar un avance.
- Coordinador: validarlo + ver "Avance de la obra".
- Admin: tablero + nuevo trabajo + corralón optimizado + Hoja de ruta.
- Síndico: Control + firmar un certificado.

Listo: la base quedó en producción con datos reales.

---

## Si algo sale mal
Restaurá el backup del paso 1:
```bash
ssh coopeapp-vps "cd ~/odoo-coop && gunzip -c ~/backup_pre_golive_AAAA-MM-DD.sql.gz | docker compose exec -T db psql -U odoo coop_piloto && docker compose restart odoo"
```
(Probá el restore en una base de prueba ANTES del piloto si nunca lo hiciste.)
