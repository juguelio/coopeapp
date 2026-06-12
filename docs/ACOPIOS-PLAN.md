# Plan — Acopios multi-corralón y órdenes de compra optimizadas

**Fecha:** 2026-06-12 · **Insumo:** Carta de Compromiso por Acopio N°54073 de
Corralón Austral S.A. (05/06/26, $2.531.110,62) + requerimiento de Juan: la coop
trabaja con 3 corralones que dan acopios, cada obra tiene los suyos.

## Cómo funciona el acopio (según la carta real)

- La coop entrega un **monto** ($2,53M) y eso **congela la lista de precios
  completa** del corralón a la fecha del acopio ("no podrán ser variados ni
  reajustados").
- Los materiales se retiran por remito y se descargan del acopio
  cronológicamente hasta cancelarlo.
- El acopio fija precios, **no reserva stock**.
- Conclusión de modelo: el acopio es **plata con lista de precios congelada**,
  no unidades. Con inflación, cada lista congelada envejece distinto → comparar
  el precio congelado del mismo material entre corralones es donde está la
  ganancia real.

## Regla de oro del optimizador

Para cada material pedido:

1. **Acopio primero.** Si uno o más corralones tienen acopio vigente con saldo,
   elegir el de **menor precio congelado** → consume menos saldo por unidad →
   el mismo acopio rinde más materiales.
2. **Saldo parcial:** si el saldo no alcanza, se parte la línea (lo que entra
   por acopio + el resto por el siguiente mejor precio).
3. **Sin acopio:** compra directa al corralón con **menor precio actual**
   (con alerta si ese precio está desactualizado).
4. **Toda asignación es explicable.** Cada línea muestra por qué:
   *"Acopio #54073 — congelado $11.300 vs $13.250 (Don Pedro) y $12.800
   actual"*. Sin caja negra: esto es lo que genera confianza.
5. **El coordinador siempre puede pisar la decisión** (elegir otro corralón por
   línea: stock, distancia, confianza). El sistema no lo bloquea: le muestra el
   costo de la decisión ("+$38.000 vs óptimo") y registra que fue manual.

El resultado se agrupa en **una orden por corralón** (retiro de acopio y/o
compra), cada una con su mensaje de WhatsApp/SMS propio.

## Backend

### `coop.acopio`
- `obra_id`, `corralon_id` (res.partner proveedor), `numero` (ej: 54073),
  `fecha`, `monto_total`, adjunto (PDF de la carta), `state`
  (vigente / agotado / cerrado).
- `saldo` computado = monto_total − Σ retiros valorizados a precio congelado.
- Constraint: los retiros nunca superan el monto.
- **Múltiples acopios por corralón** (caso real: Austral #51584 del 07/01 por
  $2,77M, #53683 del 01/04 por $4,75M y #54073 del 05/06 por $2,53M, cada uno
  con su lista congelada). La carta fija la regla de consumo: **cronológico** —
  se descarga primero el acopio más viejo. Como la lista vieja es la más
  barata (ej: mismo adhesivo $7.868 → $8.791 → $8.930), el precio vigente de
  un material en un corralón es el del **acopio activo** (el más antiguo con
  saldo). El optimizador compara ese precio activo entre corralones.

### `coop.acopio.precio` (lista congelada)
- `acopio_id`, `material_id`, `codigo_corralon`, `precio_congelado`.
- Se cargan **solo los materiales del catálogo de la coop** (el PDF tiene miles
  de ítems; importamos los ~30-80 que se usan). Carga v1: planilla/manual.
  v2: import del PDF (es generado por sistema — "System Maker's" — y parseable).

### `coop.lista.precio` (precios actuales, para compras)
- `corralon_id`, `material_id`, `precio`, `fecha`.
- Histórico → variación % entre cargas y **antigüedad visible**: en contexto
  inflacionario un precio de >15 días dispara alerta "precio viejo, confirmar".
- Referencia USD opcional (carga manual o API del dólar) como columna
  informativa; la comparación operativa es siempre en pesos del día.

### `coop.orden.corralon` (evoluciona lo ya planificado)
- Pasa a generarse **una por corralón** desde el mismo lote de pedidos
  aceptados. Campos nuevos: `tipo` (retiro_acopio / compra / mixta),
  `acopio_id` (si aplica), `ahorro_estimado`.
- Línea: pedido origen, material, cantidad, **fuente** (acopio/compra),
  precio aplicado, razón (texto generado), `asignacion_manual` (bool).
- Al confirmar entrega: descuenta saldo del acopio (si fuente=acopio) e imputa
  el gasto al rubro Materiales de la etapa (ya planificado antes).

### Algoritmo (Python puro, determinista, testeable)
Greedy por línea con orden estable: candidatos = acopios vigentes con precio
para ese material y saldo > 0, ordenados por precio congelado; luego compra al
menor precio actual. Sin solver: el problema es separable por línea (el único
acople es el saldo del acopio, que se consume en orden). Cada paso emite su
explicación. UserError si no hay precio cargado para un material pedido.

## Frontend (coordinador — ver mockup)

- **Órdenes de compra**: resumen del optimizador arriba ("asignado al menor
  costo — ahorro estimado $X"), después una tarjeta por corralón con sus
  líneas. Cada línea: fuente con chip (📦 Acopio congelado / 💲 Mejor precio) +
  botón "Cambiar" (selector de corralón con el costo de cada alternativa).
- Botón WhatsApp **por corralón** (mensajes separados).
- **Obra (socios, transparencia ACI):** tarjeta "Acopios de la obra" con saldo
  por corralón y barra de consumo. Todos ven cuánta plata congelada queda.

## Fases

1. Modelos acopio + lista congelada + saldo, carga manual de precios. Orden
   por corralón **sin** optimizador (el coordinador elige fuente a mano y ve
   los precios comparados).
2. Optimizador con explicación + ahorro estimado + override.
3. Alertas de precio viejo + variación % + referencia USD.
4. Import de listas desde PDF/planilla del corralón.

La fase 1 ya digitaliza el control del acopio (hoy: la carta en papel y la
cuenta en la cabeza de alguien). El optimizador llega cuando ya hay datos
cargados y confiables.
