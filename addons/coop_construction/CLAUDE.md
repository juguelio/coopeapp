# Módulo coop_construction

Vertical de construcción para cooperativas de trabajo. Depende de `coop_members`, `coop_payroll` y `project`.

## Modelos

- `project.project` (extendido) — obras cooperativas, identificadas con `is_coop_obra = True`
- `project.task` (extendido) — tareas de obra con categoría y cuadrilla asignada
- `coop.certificado` — certificados de avance para facturación al comitente
- `coop.work.entry` (extendido) — agrega `obra_id` para atribuir horas a una obra

## Relaciones clave

- Obra (`project.project`) → `certificado_ids` (One2many `coop.certificado`)
- Obra → `obra_work_entry_ids` (One2many inverso de `coop.work.entry.obra_id`)
- `costo_mano_obra` = `sum(obra_work_entry_ids.hours)` × `hour_rate`
- `total_certificado` = suma de certificados en estado `aprobado` o `cobrado`

## Flujo de certificados

`borrador` → `presentado` → `aprobado` → `cobrado`

El comitente puede rechazar (→ `rechazado`), el certificado vuelve a `borrador` para corrección.
Solo managers aprueban, cobran y rechazan. Cualquiera puede presentar.

## Reglas de negocio

- `hour_rate` es por obra (negociado con el comitente), no heredado de liquidaciones.
- Las obras se identifican por `is_coop_obra = True` en `project.project`.
- Un socio registra horas en `coop.work.entry` con `obra_id` → eso alimenta `costo_mano_obra`.
- Número de certificado (`numero`) es único por obra (SQL constraint).
- No hay registro de acceso por obra (transparencia ACI): todos los socios ven todos los certificados.

## XPaths que pueden necesitar ajuste post-instalación

Si al instalar Odoo reporta XPath not found:

- `views/project_project_views.xml` → `//field[@name='partner_id']`: cambiar a otro campo presente en `project.edit_project` de tu instancia (ej: `//field[@name='user_id']`).
- `views/project_task_views.xml` → `//field[@name='user_ids']`: ídem para `project.view_task_form2`.

La acción `action_coop_obras` funciona independientemente de esas extensiones: las obras son accesibles aunque falle el inheritance de las vistas estándar.

## Dependencias

```
base, mail, account, hr
       ↓
coop_members
       ↓
coop_payroll    project (Odoo nativo)
       ↓           ↓
       coop_construction
```
