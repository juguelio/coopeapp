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
```bash
cd ~/Dev/coopeapp
rsync -az -e ssh scripts/purge_demo.py coopeapp-vps:~/odoo-coop/scripts/
ssh coopeapp-vps "cd ~/odoo-coop && cat scripts/purge_demo.py | docker compose run --rm -T odoo odoo shell -d coop_piloto"
```
Imprime qué borró y, al final, `Partners demo restantes: 0`. Si quedó algún
`(aviso)`, revisalo a mano (suele ser un FK; rara vez pasa).

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
