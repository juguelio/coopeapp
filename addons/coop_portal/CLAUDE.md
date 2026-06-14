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
