# Módulo coop_members

Gestión de socios cooperativos. Es el módulo base del MVP: todos los demás dependen de él.

## Modelos

- `coop.member` — socio cooperativo con ciclo de vida completo
- `coop.contribution` — aporte, retiro, retorno o anticipo de capital social
- `res.partner` (extendido) — campo `is_coop_member` y relación inversa

## Estados del socio

`prospect` → `active` → `suspended` → `leaving` → `former`

La transición `prospect → active` requiere fecha de ingreso.
La transición `* → leaving` dispara notificación para resolución por asamblea.
Nunca eliminar socios: solo cambiar estado a `former`.

## Reglas de negocio críticas

- DNI y CUIL son únicos en toda la base de datos.
- No se puede retirar más capital del que el socio tiene acumulado.
- Un socio activo siempre tiene `date_admission` definida.
- Los aportes y retiros tienen estado propio: `draft → confirmed`. Solo los `confirmed` afectan el capital.

## Seguridad (tres grupos)

- `group_coop_member`: lee solo su propia ficha (record rule por partner_id)
- `group_coop_manager`: crea, lee y edita todos los socios. No puede eliminar.
- `group_coop_syndic`: solo lectura total. Hereda de manager.

## Cómo correr los tests

```bash
docker exec odoo-coop-app odoo --test-enable --stop-after-init -d test_db -i coop_members
```

## Qué NO tocar sin discutir

- La lógica de `_compute_totals`: de ella depende el capital social que ven los socios.
- Los record rules de seguridad: afectan la transparencia cooperativa (principio ACI 2).
- Los estados del socio: cualquier cambio tiene implicancias legales cooperativas.

## Próximo módulo que depende de este

`coop_payroll` usa `coop.member` como referencia para liquidaciones.
`coop_assembly` usa `coop.member` para registrar votos y quórum.




Quiero trabajar en este proyecto con estas premisas: # CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. 
Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. 
For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" 
If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it. Don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]

Strong success criteria let you loop independently. 
Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, 
fewer rewrites due to overcomplication, and clarifying questions come 
before implementation rather than after mistakes.
