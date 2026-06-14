# Módulo coop_construction

Vertical de construcción para cooperativas de trabajo. Depende de `coop_members`, `coop_payroll` y `project`.

## Modelos

- `project.project` (extendido) — obras cooperativas, identificadas con `is_coop_obra = True`
- `project.task` (extendido) — tareas de obra con categoría y cuadrilla asignada
- `coop.certificado` — certificados de avance para facturación al comitente
- `coop.work.entry` (extendido) — agrega `obra_id` para atribuir horas a una obra
- `coop.etapa` — proyección de pagos por etapa de obra (template del síndico Juan)
- `coop.proyeccion.gasto` — gastos planificados de una etapa, por rubro
- `coop.etapa.cuadrilla` — cálculo de mano de obra: rol × cantidad × tarifa diaria × días
- `coop.unidad.produccion` — catálogo de ítems con precio de referencia y unidad física (m², ml, m³…)
- `coop.foja.item` — foja de medición: cantidad, precio, incidencia %, avance %
- `coop.avance.medicion` — avance cargado por socio: cantidad producida + trabajo insumido (jornal/hora/tarea)
- `coop.material` — catálogo de materiales para pedidos
- `coop.pedido.material` — pedido de un socio (pendiente → aceptado/rechazado); guarda `cantidad_original` cuando el coordinador corrige

## Relaciones clave

- Obra (`project.project`) → `certificado_ids` (One2many `coop.certificado`)
- Obra → `obra_work_entry_ids` (One2many inverso de `coop.work.entry.obra_id`)
- `costo_mano_obra` = `sum(obra_work_entry_ids.hours)` × `hour_rate`
- `total_certificado` = suma de certificados en estado `aprobado` o `cobrado`

## Flujo de certificados

`borrador` → `presentado` → `aprobado` → `cobrado`

El comitente puede rechazar (→ `rechazado`), el certificado vuelve a `borrador` para corrección.
Solo managers aprueban, cobran y rechazan. Cualquiera puede presentar.

## Proyección de pagos por etapa

Replica el Excel del síndico (ficha de obra Carriqueo):

- Cada obra tiene N etapas (`coop.etapa`, número único por obra). Flujo: `planificacion` → `en_curso` → `cerrada`.
- Disponible de la etapa = `ingreso` + `saldo_etapa_anterior`.
- Gastos planificados (`coop.proyeccion.gasto`): rubro fijo (mano de obra, materiales, maquinarias, equipo técnico, g. operativos, g. administrativos), estado pendiente/pagado, flag `presupuesto_confirmado`.
- Computados: `saldo_sin_planificar` = disponible − planificado; `controlador` = disponible − pagado (lo que debería haber en cuenta).
- Resumen por rubro: vista pivot de `coop.proyeccion.gasto` (menú Gastos Planificados).
- Cuadrilla: líneas rol × cantidad × tarifa diaria × días → `total_cuadrilla`.
- Permisos: socios y síndico solo lectura (transparencia ACI), managers editan.

## Foja de medición y % productivo

Replica la FOJA_MEDICION del Excel del síndico:

- `coop.foja.item`: ítems por obra (etapa y tarea opcionales). `incidencia` = precio_total / total de la foja. `avance_pct` = ejecutado/cantidad. `aporte_pct` = incidencia × avance. `project.project.avance_fisico` = Σ aportes.
- `coop.avance.medicion`: el socio registra cantidad producida (en la U. del ítem) + trabajo insumido en unidad variable (jornal/hora/tarea). `productividad` = cantidad/trabajo. Solo los avances **validados** por un manager suman al avance físico.
- Record rules: el socio crea/edita solo sus avances en borrador; lectura abierta (transparencia ACI). Pivot de avances = productividad por socio.
- Unidades de producción (`coop.unidad.produccion`): catálogo con precio de referencia; onchange completa U. y precio en el ítem.

## Ruta crítica (CPM)

- `project.task`: `duracion_dias`, `inicio_temprano`, `fin_temprano`, `holgura`, `es_critica` (calculados, no editar a mano).
- `project.project.action_calcular_ruta_critica()`: CPM sobre `task_ids` usando `depend_on_ids` (dependencias nativas de project; activar "Dependencias de tareas" en Ajustes de Proyecto). Detecta ciclos con UserError.
- Botón en la página "Foja de Medición" de la obra (solo managers). Menú "Hoja de Ruta": lista ordenada por inicio temprano, críticas en rojo.
- El Gantt visual custom (OWL) es fase 2; estos campos (inicio/fin temprano) son su fuente de datos.

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
