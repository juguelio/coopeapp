# Preflight de foja de medición

- **Archivo:** `/Users/altostake/Dev/coopeapp/carriqueo foja medicion.xlsx`
- **Hoja elegida:** `FOJA_MEDICION`
- **Hojas disponibles:** `Nota de presentación`, `RESUMEN`, `FOJA_MEDICION`, `RESUMEN_CONVENIO mixto`, `RESUMEN_CONVENIO`, `Replanificacion CURVA`, `FOTOS`, `Copia de Certificación de tarea`, `PLANT_CURVA`, `IF_Seguimiento 4112025`, `original Proyeccion PRIMERA ETA`, `Proyeccion PRIMERA ETAPA (20%)`, `2025`
- **Fila de encabezado:** 15
- **Columnas detectadas:** cant, desc, inc, item, pu, total, uom
- **Nivel sugerido:** 1 (la planilla no declara un total en esta solapa; se sugiere el nivel de mayor importe, pero es una corazonada, no una verificación)
- **Total declarado:** —
- **Filas importables en nivel sugerido:** 7
- **Total importable en nivel sugerido:** $ 40.419.000,00

## Totales por nivel

| Nivel | Ítems | Importe |
|---:|---:|---:|
| 1 | 7 | $ 40.419.000,00 |
| 2 | 54 | $ 3.060.433,65 |

## Avisos del archivo

- Hay importes en más de un nivel de la numeración (nivel 1: 7 ítems, 40419000.00, nivel 2: 54 ítems, 3060433.65). Importar todos cuenta la obra dos veces: los rubros de nivel 1 ya contienen a sus subítems. Elegí con qué nivel te quedás.
- 167 fila(s) con algo raro para revisar a mano.

## Avisos de filas que se importarían

- Fila 35 (2.0): La planilla dice unitario 1094101.78 pero importe/cantidad da 6650000.00. Se usó el importe. Revisalo.
- Fila 48 (3.0): La planilla dice unitario 0.00 pero importe/cantidad da 3500000.00. Se usó el importe. Revisalo.
- Fila 52 (4.0): La planilla dice unitario 0.00 pero importe/cantidad da 3000000.00. Se usó el importe. Revisalo.
- Fila 56 (5): La planilla dice unitario 0.00 pero importe/cantidad da 5200000.00. Se usó el importe. Revisalo.
- Fila 68 (6): La planilla dice unitario 0.00 pero importe/cantidad da 8381000.00. Se usó el importe. Revisalo.
- Fila 72 (10.0): La planilla dice unitario 0.00 pero importe/cantidad da 10400000.00. Se usó el importe. Revisalo.

## Decisión humana requerida

Este informe no importa ni corrige la foja. Antes de crear ítems en una obra,
confirmar que el nivel sugerido no duplica importes y que los avisos de cada fila
representan el cómputo real, no una plantilla o una fórmula rota.
