# Módulo coop_assembly

Asambleas cooperativas con votaciones y actas automáticas. Depende de `coop_members`.

## Modelos

- `coop.assembly` — asamblea con convocatoria, quórum, socios presentes y acta
- `coop.vote` — votación dentro de una asamblea con resultado automático

## Flujo de una asamblea

1. Se crea en estado `draft` con orden del día
2. Se registran los socios presentes en la pestaña "Socios presentes"
3. El sistema calcula el quórum automáticamente
4. Si hay quórum, se puede pasar a `open` con "Iniciar asamblea"
5. Se cargan las votaciones con los votos a favor, en contra y abstenciones
6. El resultado de cada votación se calcula automáticamente según el tipo de mayoría
7. Se genera el acta automáticamente con "Generar acta"
8. Se cierra con "Cerrar asamblea" → estado `closed`

## Tipos de mayoría soportados

- Simple: más votos a favor que en contra
- Absoluta: más del 50% del total
- Dos tercios: 66.67% o más
- Unanimidad: cero votos en contra y cero abstenciones

## Reglas de negocio críticas

- No se puede iniciar una asamblea sin quórum.
- Todos los socios activos pueden leer las asambleas (transparencia total).
- Solo el admin puede crear y gestionar asambleas.
- El acta se genera automáticamente pero se puede editar antes de cerrar.
- Las asambleas cerradas no se pueden eliminar, solo leer.

## Principios ACI que implementa

- Control democrático (principio 2): un socio un voto, quórum obligatorio
- Transparencia (principio 5): todos los socios ven todas las asambleas y sus resultados
