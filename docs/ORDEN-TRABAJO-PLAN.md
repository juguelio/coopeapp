# Plan — Orden de trabajo → Relevamiento → Presupuesto

**Fecha:** 2026-06-12 · Es el **pipeline pre-obra**: lo que pasa desde que un
cliente pide un trabajo hasta que se convierte en obra con etapas.

**Decisión de roles:** "Manager" pasa a llamarse **Administrador** en toda la
app (en Odoo solo cambia la etiqueta del grupo `group_coop_manager`; el id
técnico queda para no romper permisos). El Administrador tiene la máxima
información: tablero completo, ruta crítica, acopios, economía, y además
gestiona este flujo comercial.

## Flujo

```
Cliente pide trabajo
   ↓
1. ORDEN DE TRABAJO (la crea el Administrador)
   memoria descriptiva de etapas + materiales + herramientas
   + gastos impositivos / administrativos / logística
   ↓
2. RELEVAMIENTO (lo asigna a un socio)
   el socio va al lugar y carga desde la app: medidas, fotos, observaciones
   ↓
3. PRESUPUESTO (lo arma el Administrador con el relevamiento cargado)
   líneas por categoría + IVA según tipo de factura (A/B/C)
   ↓ enviar al cliente (PDF + WhatsApp)
4. APROBADO → se crea la OBRA (project) con sus etapas desde la memoria
   descriptiva. Rechazado/vencido → queda el historial.
   ↓
5. ASIGNAR COORDINADOR (Administrador): elige quién la lleva, viendo la
   carga de cada coordinador (cuántas obras tiene). La obra aparece en la
   app del coordinador elegido. Un coordinador puede tener varias obras.
```

> Backend del paso 5: `coordinador_id` en la obra (renombrar la etiqueta del
> actual `capataz_id` de `project.project`) + grupo `group_coop_coordinador`
> (entre member y manager, ya previsto en el plan de pedidos). Las bandejas
> del coordinador (avances/pedidos) filtran por sus obras.

## Backend

### `coop.orden.trabajo`
- `name` (secuencia OT-2026-001), `cliente_id` (res.partner), `descripcion`,
  `ubicacion`, `fecha_recepcion`, `administrador_id`.
- `state`: `recibida → relevamiento → presupuestada → enviada → aprobada /
  rechazada / vencida`. Al aprobar: acción que crea `project.project`
  (is_coop_obra) + `coop.etapa` por cada etapa de la memoria.
- **Memoria descriptiva** = One2many `coop.ot.etapa`: secuencia, nombre,
  descripción, materiales estimados (texto o líneas), herramientas necesarias.
  Es el borrador de las `coop.etapa` reales.
- `relevador_id` (coop.member asignado), `relevamiento_id`, `presupuesto_ids`.

### `coop.relevamiento`
- `orden_id`, `member_id`, `fecha`, `medidas` (líneas: concepto / valor / unidad
  — ej: "frente 12,4 ml", "superficie a pintar 180 m²"), `observaciones`,
  fotos (`ir.attachment`), `state`: pendiente → cargado → validado.
- El socio lo carga desde la app (wizard simple). El Administrador no
  presupuesta hasta que está cargado — la app se lo bloquea con el motivo
  visible ("esperando relevamiento de Carlos").

### `coop.presupuesto`
- `orden_id`, `numero`, `fecha`, `validez_dias` (clave con inflación: default
  7-10 días), `state`: borrador → enviado → aprobado / rechazado / vencido.
- Líneas con `categoria`: materiales / mano de obra / herramientas-equipos /
  gastos impositivos / gastos administrativos / logística. Cantidad, precio,
  subtotal. Las líneas de materiales pueden tirar del catálogo + lista de
  precios vigente (y del acopio si la obra ya tiene).
- **Impuestos según comprobante** (`tipo_factura`):
  - **A** (cliente responsable inscripto): neto + IVA 21% discriminado
    (10,5% para ítems que correspondan).
  - **B** (consumidor final / monotributista): IVA incluido en el total.
  - **C / recibo**: sin discriminar (si la coop fuera exenta — confirmar
    situación fiscal real de la coop con el contador antes de codear esto).
  - Campo `iva_alicuota` por línea; totales computados: neto, IVA, total.
- Salida: PDF QWeb con membrete de la coop + texto listo para WhatsApp.
- Versionado: si el cliente pide cambios se genera presupuesto v2 sobre la
  misma OT; el historial queda.

### Permisos
- Administrador: todo el flujo. Coordinador: lectura. Socio: ve las OT donde
  es relevador y carga su relevamiento (record rule igual que avances).
- Síndico: lectura total.

## Frontend (en la app — ver mockup)

**Administrador:**
- Tarjeta "Órdenes de trabajo" en el tablero con contador por estado.
- Lista de OTs → detalle: memoria descriptiva, estado del relevamiento,
  botón asignar relevador, y el presupuesto con desglose por categoría +
  selector factura A/B (recalcula IVA en vivo) + "Enviar al cliente".

**Socio (relevador):**
- Tarjeta en Inicio: "Te asignaron un relevamiento" → wizard: medidas (concepto
  + número + unidad, repetible), fotos, observaciones → enviar. Mismo patrón
  de 1 dato por paso que cargar avance.

## Qué NO entra en v1
Facturación electrónica AFIP (el presupuesto no es factura; la factura real
sigue saliendo del circuito contable actual), firma del cliente en la app,
seña/cobranza. Se anotan para después.

## Orden de implementación
1. `coop.orden.trabajo` + memoria descriptiva + estados (sin presupuesto).
2. Relevamiento con carga desde la app (wizard socio).
3. Presupuesto con categorías + IVA A/B + PDF + envío.
4. "Aprobar → crear obra + etapas" (cierra el círculo con todo lo ya hecho).
