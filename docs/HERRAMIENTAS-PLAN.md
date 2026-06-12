# Plan — Herramientas: inventario, asignación, services e incidentes

**Fecha:** 2026-06-12 · Requerimiento: el coordinador selecciona las
herramientas a usar por obra; base de datos de todas las herramientas;
services/mantenimientos según cada herramienta; y operario/coordinador
reportan rotura o pérdida (de herramientas **y** de materiales).

## Decisión técnica: extender `maintenance` (módulo nativo de Odoo)

Odoo Community ya trae el módulo **maintenance**: equipos con categoría,
responsable, número de serie, **mantenimiento preventivo con frecuencia en
días** (genera la solicitud sola cuando vence) y solicitudes correctivas con
etapas. No reinventamos eso — lo extendemos:

### `maintenance.equipment` (extendido) = la herramienta
- Campos nuevos: `obra_id` (dónde está), `coordinador_responsable_id`,
  `estado_coop` (disponible / en obra / en service / **rota / perdida**),
  `valor_reposicion`, foto, código de etiqueta (QR a futuro).
- Lo nativo ya cubre: categoría (eléctrica/manual/maquinaria), marca, modelo,
  serie, fecha de compra, proveedor, **frecuencia de preventivo** y la fecha
  del próximo service calculada.

### Services y mantenimientos
- **Preventivo:** se configura por herramienta (la hormigonera cada 90 días,
  la amoladora cada 180…). Odoo genera la solicitud al vencer → aparece como
  alerta en la app del coordinador que la tiene y del administrador.
- **Correctivo:** la rotura reportada desde la app crea una
  `maintenance.request` directamente.
- Costo del service/reparación → se imputa como gasto (rubro Maquinarias y
  Herramientas de la etapa — ya existe en la proyección). Cierra el círculo
  económico.

### `coop.asignacion.herramienta` (nuevo, simple)
- herramienta, obra, quién la lleva, fecha retiro / fecha devolución.
- Historial de uso por herramienta y por obra. El coordinador "selecciona
  herramientas para la obra" = crea asignaciones desde la app; al terminar,
  devuelve. Si una herramienta tiene service vencido, la app avisa al
  asignarla ("llevala, pero debe service" o bloquear si el admin lo configura).

### `coop.incidente` (nuevo) — rotura / pérdida
- `tipo`: rotura herramienta / pérdida herramienta / rotura material /
  pérdida material.
- Si herramienta: `equipment_id` → al validarse cambia su `estado_coop` y si
  es rotura crea la solicitud de reparación.
- Si material: `material_id` + cantidad → genera el ajuste como gasto/merma
  de la etapa (la merma visible es parte del control de uso → confianza).
- `obra_id`, quién reporta (cualquier socio), foto, descripción, estado:
  `reportado → revisado (coordinador) → resuelto (admin)`.
- Sin culpa automática: el incidente registra el hecho; qué se hace (reponer,
  descontar, asamblea) es decisión humana documentada en el registro.

## Permisos
- **Socio:** reporta incidentes (de su obra), ve las herramientas de su obra.
- **Coordinador:** asigna/devuelve herramientas de sus obras, revisa
  incidentes, pide service.
- **Administrador:** inventario completo, configura frecuencias de preventivo,
  resuelve incidentes, da de baja (rota/perdida definitiva), ve el costo
  anual de mantenimiento por herramienta (¿conviene reparar o reponer?).
- Transparencia: todos ven el inventario y su estado (lectura).

## En la app (ver mockup)
- **Coordinador — Inicio:** tarjeta "🔧 Herramientas" de la obra seleccionada
  (cuántas tiene, alerta de service vencido) → pantalla: lista con estado,
  "➕ Llevar herramienta" (selector de disponibles), "Devolver" y "⚠️ Reportar".
- **Socio — Obra:** botón "⚠️ Reportar rotura o pérdida" → wizard 2 pasos:
  ¿qué pasó? (4 opciones grandes) → ¿cuál? + foto + nota → "le avisamos al
  coordinador".
- **Administrador — Inicio:** alerta "2 services vencidos · 1 incidente sin
  revisar"; detalle en el backend (inventario, historial, costos — Odoo
  maintenance ya trae sus vistas).

## Fases
1. Extender `maintenance` + inventario cargado + asignación por obra.
2. Incidentes (rotura/pérdida) desde la app + imputación de mermas.
3. Preventivos configurados + alertas en app + costo por herramienta.
