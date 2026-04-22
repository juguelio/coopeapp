# coopeapp — Plataforma de gestión cooperativa

Sistema de gestión para cooperativas de trabajo construido sobre Odoo 18 Community.
52 cooperativas interesadas, 7 piloto en Neuquén. Arranca por construcción.

**Repo local:** `~/Documents/coopeapp/` — todos los paths en este archivo son relativos a esa raíz.

## Stack
- Odoo 18 Community + Docker en VPS Hetzner (178.105.15.189)
- Python 3.11, PostgreSQL 16
- Localización argentina (desactivada temporalmente, pendiente de fix)

## Estructura
addons/
  coop_members/      # Socios, aportes, capital social — MÓDULO BASE
  coop_payroll/      # Liquidaciones transparentes — depende de coop_members
  coop_assembly/     # Asambleas, votaciones, actas — depende de coop_members
  coop_construction/ # Obras, certificados de avance — depende de coop_members + coop_payroll + project

## Deploy al VPS
# Correr desde ~/Documents/coopeapp/
scp -r addons/MODULO/ odoo-admin@178.105.15.189:~/odoo-coop/addons/
ssh odoo-admin@178.105.15.189
cd ~/odoo-coop && docker compose run --rm odoo odoo -u MODULO -d coop_piloto --stop-after-init && docker compose up -d

## Reglas de comportamiento

### 1. Think Before Coding
- Explicitá suposiciones antes de implementar
- Si hay múltiples interpretaciones, presentalas. No elijas en silencio.
- Si algo es confuso, pará y preguntá antes de escribir código.

### 2. Simplicity First
- Mínimo código que resuelve el problema. Nada especulativo.
- Sin features más allá de lo pedido.
- Si escribís 200 líneas y podría ser 50, reescribilo.

### 3. Surgical Changes
- Tocá solo lo que tenés que tocar.
- No "mejores" código adyacente que no está roto.
- Cada línea cambiada debe trazarse directamente al pedido.

### 4. Odoo específico — CRÍTICO
- Nunca escribir Python genérico. Siempre Odoo idiomático.
- Modelos heredan de models.Model, campos son descriptores declarativos.
- Vistas en XML, permisos en CSV, nunca lógica de UI en Python.
- Si no sabés cómo hacer algo idiomáticamente en Odoo, preguntá antes de inventar.
- Un módulo que no sigue convenciones de Odoo directamente no instala.

### 5. Goal-Driven
- Antes de cada tarea, definir criterio de éxito verificable.
- Para bugs: escribir test que lo reproduce, después arreglarlo.
- Para features: definir qué tiene que pasar cuando está listo.

## Principios cooperativos (filtro de decisiones)
Toda feature nueva se valida contra los 7 principios ACI.
Si debilita alguno, no se implementa sin discusión.
Ver .claude/rules/cooperative-principles.md para detalle.

## Comandos útiles
# En el VPS (después de ssh odoo-admin@178.105.15.189, cd ~/odoo-coop):
docker compose logs -f odoo
docker compose restart odoo
docker compose run --rm odoo odoo -u MODULO -d coop_piloto --stop-after-init
