# coopeapp — Plan de release a v1.0 (producto completo)

**Fecha:** 2026-06-14 · Define qué significa "100%" y el camino para llegar.
Cada hito es codeable de punta a punta (backend + portal + datos demo +
deploy) y tiene un criterio de "listo" verificable.

## Dónde estamos (≈85% mínimo usable · ≈52% del completo)

YA EN PRODUCCIÓN (https://www.coopeapp.com.ar/app):
- Base Odoo 18: `coop_members`, `coop_payroll`, `coop_books`.
- `coop_construction` v18.0.1.4.0: obras, etapas, foja de medición, avances por
  socio, ruta crítica (CPM), certificados con **firma digital + hash**, pedidos
  de materiales (catálogo + pedido).
- `coop_assembly` v18.0.1.1.0: asambleas, votaciones, **voto secreto individual**
  (coop.ballot) desde el celular.
- `coop_portal` v18.0.0.3.0: los **4 roles operan en la app**:
  - Socio: cargar avance, pedir materiales, mi plata, obra, votar.
  - Coordinador: validar avances, bandeja de pedidos.
  - Síndico: panel de fiscalización, firma de certificados, auditoría.
  - Administrador: tablero multi-obra, ruta crítica, reportes.
- Tooling: `deploy.sh` (1 password), `load_demo_data.py` idempotente,
  demo en `/demo`, manual de usuario PDF.

## Hitos para llegar al 100%

### M1 — Cerrar el loop de materiales: orden al corralón ⏳ (lo más cerca)
- **Backend:** `coop.orden.corralon` (corralon_id, obra_id, pedido_ids
  aceptados, estado borrador→enviada→confirmada→entregada, `mensaje` armado por
  plantilla). Al marcar entregada → imputa gasto al rubro Materiales de la etapa.
- **Portal coordinador:** consolidar los pedidos aceptados por corralón →
  vista previa del mensaje → botón **WhatsApp (`wa.me`)** y SMS, una orden por
  corralón.
- **Done:** el coordinador junta los pedidos aceptados y manda una orden real
  por WhatsApp; queda registrada y el gasto aparece en la etapa.

### M2 — Acopios multi-corralón + optimizador de precios
- **Backend:** `coop.acopio` (plata con lista de precios congelada, saldo
  computado), `coop.acopio.precio`, `coop.lista.precio` (precios actuales con
  antigüedad). Optimizador greedy **explicable**: acopio de menor precio
  congelado primero, compra al mejor precio actual después; override del
  coordinador con costo visible.
- **Portal:** órdenes divididas por corralón con la razón de cada línea y el
  ahorro estimado; alertas de precio viejo (inflación).
- **Done:** cargás 2-3 acopios reales (cartas Austral), pedís materiales y el
  sistema asigna al menor costo con la explicación; el coordinador puede pisar.

### M3 — Pipeline comercial: orden de trabajo → relevamiento → presupuesto
- **Backend:** `coop.orden.trabajo` (memoria descriptiva por etapas),
  `coop.relevamiento` (el socio carga medidas/fotos desde la app),
  `coop.presupuesto` (líneas por categoría, **IVA según factura A/B/C**,
  validez corta por inflación) + PDF QWeb. Aprobar → crea la obra + etapas +
  asigna coordinador.
- **Portal:** admin gestiona OTs y presupuesta; socio carga el relevamiento.
- **Done:** del pedido de un cliente sale un presupuesto en PDF; al aprobarlo
  nace la obra con sus etapas.
- **Antes de codear:** confirmar situación fiscal real de la coop con el contador.

### M4 — Herramientas: inventario, services e incidentes
- **Backend:** extender el módulo nativo `maintenance` (preventivos por
  frecuencia, correctivos). `coop.asignacion.herramienta` (por obra, historial),
  `coop.incidente` (rotura/pérdida de herramienta **y material**). Costos de
  service imputados al rubro Maquinarias y Herramientas.
- **Portal:** coordinador asigna/devuelve herramientas y pide service; cualquier
  socio reporta rotura/pérdida (merma visible como gasto, sin culpa automática).
- **Done:** una herramienta con service vencido avisa; un socio reporta una
  rotura y queda registrada con su impacto económico.

### M5 — Asamblea digital completa (acta legal)
- **Backend:** `coop.assembly.point` (orden del día estructurado), acta QWeb con
  el **formato exacto del libro** (Acta N°32: autoridades con DNI, quórum, ley
  20.337, resoluciones), firmas con hash, asistencia self-service.
- **Portal:** "estoy presente", puntos como tarjetas, secretario arma el acta.
- **Done:** una asamblea genera el acta lista para copiar al libro rubricado;
  los socios marcan asistencia y votan; el síndico firma.
- **Pospuesto a v1.1:** audio + transcripción.

### M6 — Ruta crítica editable por oficio + reportes unificados
- **Portal admin:** editor de tareas (duración, dependencias, oficio) con
  recálculo CPM y aviso anti-cadena-falsa; carriles por oficio (el atraso de un
  oficio no contagia a otro).
- **Backend:** `coop.operacion` (vista SQL UNION de todas las operaciones) →
  reportes con rango/filtros + export Excel/PDF nativo de Odoo.
- **Done:** el admin edita la ruta desde el celular y ve el impacto por carril;
  los reportes salen filtrados y exportables.

### M7 — Hardening + PWA (para producción real)
- `group_coop_coordinador` real + record rules (hoy el coordinador valida vía
  capataz_id + sudo verificado).
- Login **teléfono + PIN** con rate-limiting (hoy login Odoo estándar).
- **PWA:** `manifest.json` + service worker + **cola offline** para cargar
  avances sin señal en obra (se sincroniza al volver la red).
- Tests automatizados de los flujos críticos; resolver deuda técnica anotada
  (warning de computed/store en `coop_assembly`); verificar backups del VPS.
- **Done:** instalable como ícono, funciona sin señal para cargar avances,
  permisos correctos por rol, tests verdes.

## Orden sugerido y esfuerzo

1. **M1** (orden al corralón) — chico, cierra algo medio hecho.
2. **M3** (OT→presupuesto) — alto valor comercial, grande.
3. **M2** (acopios + optimizador) — depende de M1.
4. **M4** (herramientas) — independiente.
5. **M5** (asamblea completa) — independiente, valor para síndicos.
6. **M6** (ruta editable + reportes) — pulido.
7. **M7** (hardening + PWA) — antes del lanzamiento masivo.

Cada hito es 1-2 sesiones de trabajo. v1.0 = M1–M6 codeados y deployados + M7
hardening. M5 audio y features avanzadas → v1.1.

## Lo que NO es código (para vender, no para construir)
Onboarding de las 7 piloto, capacitación presencial, precios/contrato, soporte,
respaldo institucional (Juan/Federación). Eso es go-to-market, va aparte.
