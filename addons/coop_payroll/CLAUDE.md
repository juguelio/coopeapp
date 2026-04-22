# Módulo coop_payroll

Liquidaciones transparentes a socios. Depende de `coop_members`.

## Modelos

- `coop.payroll` — liquidación por período por socio
- `coop.advance` — anticipo pedido por un socio, aprobado por admin
- `coop.work.entry` — registro de horas trabajadas en una liquidación

## Flujo de estados de una liquidación

`draft` → `review` → `approved` → `paid`

El paso clave es `review`: el socio puede ver la liquidación, agregar observaciones y marcar conformidad (`member_agrees = True`) antes de que se apruebe. Esto implementa el principio ACI de control democrático y transparencia.

## Reglas de negocio críticas

- El neto no puede ser negativo al aprobar.
- Los anticipos solo se descuentan si están en estado `approved`.
- El socio puede crear anticipos pero no aprobarlos (solo el admin puede).
- El socio solo ve sus propias liquidaciones (record rule).
- Una liquidación pagada no se puede modificar.

## Fórmula de cálculo

```
gross = (total_hours × hour_rate) + bonus_amount
net = gross - deduction_amount - total_advances
```

La fórmula es simple por ahora. En fases futuras se puede extender para incluir retornos por excedentes según estatuto.

## Seguridad

- Socio: lee y escribe sus propias liquidaciones, puede crear anticipos, NO puede aprobar.
- Admin: crea, aprueba, paga y cancela liquidaciones. Aprueba anticipos.
- Síndico: solo lectura total.

## Próximo módulo que depende de este

`coop_assembly` no depende de `coop_payroll` directamente, pero las votaciones de distribución de excedentes impactan en las fórmulas de liquidación.
