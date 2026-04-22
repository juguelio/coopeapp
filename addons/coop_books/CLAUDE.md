# Módulo coop_books

Generación de libros cooperativos obligatorios para INAES/IPCyMER. Depende de `coop_members`, `coop_assembly`, `coop_payroll` y `account`.

## Modelo

- `coop.book.export` (TransientModel) — wizard que parametriza la generación: tipo de libro y rango de fechas.

## Libros implementados

| ID libro             | Nombre oficial                          | Fuente de datos             |
|----------------------|-----------------------------------------|-----------------------------|
| `registro_asociados` | Registro de Asociados                   | `coop.member`               |
| `actas_asamblea`     | Actas de Asamblea                       | `coop.assembly` (ordinary/extraordinary) |
| `actas_consejo`      | Actas del Consejo de Administración     | `coop.assembly` (board)     |
| `liquidaciones`      | Liquidaciones a Socios                  | `coop.payroll`              |
| `inventario_balance` | Inventario y Capital Social             | `coop.contribution`         |

**Nota sobre inventario_balance**: registra aportes y retiros confirmados. No es el balance contable completo — ese se obtiene desde el módulo `account` estándar de Odoo.

## Flujo de uso

1. Manager o Síndico abre Cooperativa → Libros INAES → Generar Libro
2. Selecciona tipo de libro y rango de fechas
3. Hace clic en "Generar PDF"
4. El wizard llama al `ir.actions.report` correspondiente y retorna el PDF

## Seguridad

Solo `group_coop_manager` y `group_coop_syndic` pueden acceder. Los socios comunes no tienen acceso al wizard.

## Qué NO tocar sin discutir

- Los métodos `get_*` del wizard: de ellos dependen los datos que aparecen en los PDFs.
- El mapeo `BOOK_REPORT_MAP`: debe coincidir exactamente con los `id` de los `ir.actions.report`.

## Limitación conocida

El libro "Inventario y Balance" del INAES incluye también el balance contable patrimonial. Esa parte requiere integración con `account.move` y está fuera del scope del MVP. Está anotado en el PDF del reporte.
