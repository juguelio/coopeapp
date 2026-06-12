# Plan — Asamblea digital (coop_assembly + app de socios)

**Fecha:** 2026-06-12 · **Insumo:** foto del Acta N°32 del libro de la Coop. Unión
de los Andes Patagónicos (todo manuscrito) + módulo `coop_assembly` existente.

> **DECISIÓN 2026-06-12:** el audio + transcripción (sección 4) queda para una
> **futura actualización**. Alcance actual: pasos 1-3 (puntos, ballots,
> asistencia, acta legal, firmas con hash).

## Qué hacen hoy a mano (y qué automatizamos)

| Hoy (a mano) | Con la app |
|---|---|
| Convocatoria por WhatsApp/papel | Tarjeta en Inicio + orden del día por puntos |
| Lista de presentes y cálculo de quórum | "Estoy presente" en el celular; quórum en vivo (ya existe el cálculo) |
| Voto a mano alzada, conteo manual | Voto individual desde el celular, resultado automático por tipo de mayoría (ya existe) |
| Grabar audio con un celular suelto | Botón REC en la app del secretario; el audio queda adjunto al punto tratado |
| Escuchar el audio y transcribir | Transcripción automática → borrador de deliberación por punto |
| Redactar el acta con formato legal | Acta generada con el formato exacto del libro (ver plantilla abajo) |
| Imprimir, firmar, pegar/copiar al libro | PDF + texto listo para copiar; registro de firmas en la app |

**Lo que NO cambia:** el libro de actas rubricado sigue siendo el documento
legal (ley 20.337 / INAES). La app no lo reemplaza: **prepara el acta perfecta**
para que el secretario solo la pase al libro. La firma en la app es firma
electrónica interna (quién, cuándo, hash del texto) — da confianza y trazabilidad,
no reemplaza la firma en el libro.

## Backend (extensiones a coop_assembly)

### 1. `coop.assembly.point` — orden del día por puntos (nuevo)
Hoy `agenda` es un HTML suelto. Pasa a puntos estructurados:
- `assembly_id`, `sequence`, `name` (el tema), `descripcion`
- `state`: pendiente → en debate → resuelto
- `vote_id` (Many2one a `coop.vote`, opcional — no todo punto se vota)
- `audio_attachment_id` (grabación del debate de ese punto)
- `transcripcion` (Text, llenada por el job de transcripción)
- `resolucion` (Text — lo que quedó decidido, editable por el secretario)

### 2. `coop.ballot` — voto individual (nuevo)
Hoy `coop.vote` carga totales a mano. Para votar desde el celular:
- `vote_id`, `member_id` (unique juntos), `choice` (si/no/abstencion), timestamp
- Los totales de `coop.vote` pasan a computados desde ballots (con fallback
  manual para asambleas sin celulares).
- **Voto secreto:** record rule — los ballots individuales los ve solo el
  sistema; socios y consejo ven solo totales. El socio ve únicamente su propio voto.

### 3. Asistencia self-service
- Controller del portal: "Estoy presente" agrega al socio a `attendee_ids`
  mientras la asamblea está convocada/abierta. El secretario puede corregir.

### 4. Audio → transcripción
- **Captura:** MediaRecorder API del navegador (funciona en Chrome/Safari
  mobile), formato opus/webm (~30 MB por hora). Un REC por punto del orden del
  día (mejor que un audio de 3 horas: la transcripción queda ya seccionada).
  Subida como `ir.attachment` al cerrar cada punto; si no hay señal, cola local
  y sync después.
- **Transcripción:** job asíncrono (cron) que toma audios pendientes:
  - **v1 — API externa** (Whisper de OpenAI o Groq): ~USD 0,40 por asamblea de
    una hora, español excelente, cero carga en el VPS (CX22 de 4GB no aguanta
    un modelo local junto a Odoo+Postgres).
  - **v2 opcional — whisper.cpp local** en un worker aparte si la privacidad lo
    exige o el volumen crece. La interfaz queda igual; solo cambia el proveedor.
- La transcripción cruda va al punto; el secretario la edita a `resolucion`.
  Nunca se publica transcripción sin revisión humana.

### 5. Acta con formato legal (QWeb report)
Plantilla calcada del libro real (Acta N°32):

> ACTA N° {n}. En San Martín de los Andes, provincia del Neuquén, a los {día}
> días del mes de {mes} de {año}, siendo las {hh:mm} hs, en la sede de la
> Cooperativa de Trabajo {nombre}, sita en {dirección}, se reúne {órgano}.
> Presidente: {nombre} DNI {dni}. Secretario: {nombre} DNI {dni}. Tesorero: …
> Presentes: {n} socios de {total} ({pct}%), con quórum suficiente conforme
> art. {n} del estatuto y ley 20.337. ORDEN DEL DÍA: {puntos}. {por cada punto:
> deliberación resumida + resolución + resultado de votación (a favor/en
> contra/abstenciones)}. Sin más temas que tratar, siendo las {hh:mm} hs se da
> por finalizada la reunión, firmando al pie los asistentes designados.

- Número de acta: secuencia automática por libro (asambleas / consejo).
- Los DNI salen de `coop.member.dni` (ya existe).
- Salida: PDF para imprimir + botón "copiar texto" para transcribir al libro.
- `action_generate_minutes()` existente se reescribe sobre los puntos.

### 6. Registro de firmas (`coop.acta.firma`)
- `assembly_id`, `member_id`, `rol` (presidente/secretario/síndico), timestamp,
  `hash_acta` (SHA-256 del texto al momento de firmar — si el acta cambia
  después, las firmas quedan invalidadas visiblemente).
- Cumple el objetivo de Juan: confianza y menos impresiones. La firma digital
  con certificado (ley 25.506) queda fuera de alcance por ahora.

## Frontend (app de socios — ver mockup actualizado)

**Socio** — página de asamblea con todo en una columna:
1. Cabecera: fecha, lugar, estado, barra de quórum en vivo
2. Botón "✋ Estoy presente" (solo durante la asamblea)
3. Orden del día como tarjetas: cada punto muestra su estado
   (⏳ pendiente / 🔴 en debate / votar AHORA / ✓ resuelto con resultado)
4. Votar = una pregunta, tres botones (ya en mockup)
5. Al cerrar: "Acta disponible" para leer

**Secretario/presidente** — misma página + controles:
- Abrir asamblea (bloqueado sin quórum — regla ya existente)
- Por punto: ▶️ iniciar debate → 🎙️ REC con timer visible → ⏹️ cerrar punto
  → abrir votación
- Al final: generar borrador → revisar (la edición fina puede hacerse en Odoo
  backend si es larga) → firmar → publicar

**Síndico (Juan):** todo en lectura + su firma.

## Orden de implementación

1. Puntos del orden del día + ballots + asistencia self-service (sin audio) —
   ya digitaliza el 70% del trabajo manual
2. Acta QWeb con formato legal + secuencia + copiar/PDF
3. Firmas con hash
4. Audio REC + transcripción por API
5. (Si hace falta) transcripción local

Cada paso es deployable solo. El 1 y 2 no tienen dependencias externas ni
costo; el 4 es el único que requiere decidir proveedor de transcripción.
