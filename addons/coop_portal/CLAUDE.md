# Módulo coop_portal

App mobile-first para socios en `/app`, servida por el mismo Odoo. Depende de
`coop_construction`. Sin modelos propios: solo controllers + QWeb.

## Rutas

Socio (`controllers/portal.py`):
- `/app` — home (últimas cargas; si coordina obras muestra accesos a sus bandejas)
- `/app/cargar` → `/cantidad` → `/trabajo` → POST `/confirmar` — wizard de
  avance en 3 pasos, crea `coop.avance.medicion` en borrador
- `/app/plata` — liquidaciones (`coop.payroll`) + producción validada
- `/app/obra` — avance físico + etapa en curso + botón pedir materiales
- `/app/pedir` → `/cantidad` → POST `/confirmar` — wizard pedir material,
  crea `coop.pedido.material` en pendiente

Administrador (`controllers/admin.py`, rol = `member.role == 'manager'`):
- `/app` redirige a `/app/admin` si es admin (nav: Tablero · Ruta · Reportes · Asamblea)
- `/app/admin` — tablero multi-obra: cartera (avance %, saldo sin planificar,
  controlador por etapa en curso), tareas críticas, pendientes del equipo
- `/app/admin/ruta` — ruta crítica de toda la cartera (tareas es_critica)
- `/app/admin/reportes?rango=hoy|semana|mes` — operaciones del período
  (avances + pedidos + gastos) con totales ($ gastado, m²). NO valida nada.

Síndico (`controllers/sindico.py`, rol = `member.role == 'syndic'`):
- `/app` redirige a `/app/control` si el usuario es síndico (nav propia:
  Control · Auditoría · Asamblea · Firmar)
- `/app/control` — panel de fiscalización (certs a firmar, asamblea, obras en rojo)
- `/app/certificados` + `/app/firmar` + POST `/confirmar` — firma digital de
  certificados (`coop.certificado.action_firmar`, hash SHA-256; `firma_valida`
  se invalida si cambia un número)
- `/app/auditoria` — pista inmutable: avances validados + pedidos + firmas,
  ordenado por fecha, solo lectura

Asamblea (`controllers/asamblea.py`):
- `/app/asamblea` — asamblea en curso (state open) con sus puntos; muestra
  estado de cada votación y si ya votaste
- `/app/votar` (vote_id) + POST `/confirmar` — voto secreto: crea `coop.ballot`
  (único por socio/votación). Nadie ve el voto de otro (record rule); los
  totales viven en `coop.vote`, sincronizados desde los ballots con sudo.

Coordinador (`controllers/coordinador.py`):
- `/app/validar` + POST `/accion` — bandeja de avances en borrador de SUS obras
  (las que coordina = `capataz_id`); valida o devuelve al socio
- `/app/pedidos` + POST `/accion` — bandeja de pedidos pendientes; acepta /
  rechaza / corrige cantidad

## Seguridad del coordinador

- "Coordinador de una obra" = `project.project.capataz_id == member` (hasta que
  exista `group_coop_coordinador`).
- Las acciones del coordinador (validar avance, aceptar pedido) **verifican en
  el controller** que el member es capataz de la obra del registro, y escriben
  con `sudo()`. Deuda: mover a `group_coop_coordinador` + record rule cuando se
  cree el grupo.

## Reglas del módulo

- **Lecturas con `sudo()` filtrado por pertenencia** (member → sus obras):
  los socios no tienen ACL sobre `project.*`. Nunca exponer datos sin filtrar
  por el member del usuario logueado.
- **Escrituras SIEMPRE como el usuario** (`request.env[...].create`): la ACL
  y la record rule (solo propio + borrador) son la garantía real.
- `_member()`: resuelve `coop.member` por `partner_id.user_ids`. Sin member →
  template `sin_socio`.
- Login: el estándar de Odoo por ahora. PIN por teléfono = iteración futura
  (requiere rate-limiting serio antes de exponerlo).
- Diseño: mismo design system que `docs/mockup-ui-socios.html` (CSS inline en
  el template `layout`). Barra fija: Inicio · Cargar · Mi plata · Obra.
- UI de coordinador/admin: fase 3 (validar, pedidos, tablero) — ver
  `docs/UI-UX-PLAN.md`.

## Deploy

./scripts/deploy.sh coop_portal   (primera vez: instalar con -i en vez de -u)
