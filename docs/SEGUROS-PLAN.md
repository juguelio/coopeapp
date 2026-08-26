# Plan — Seguros y vencimientos

**Fecha:** 2026-08-24 · **Estado:** especificación, sin código.
**Origen:** pedidos 4, 5 y 6 de la reunión con Germán.
**Proyecto:** P3 en `01-Projects/coopeapp/Proyectos-2026-08-24.md`.

Este documento es la pasada de diseño. No propone escribir modelos todavía:
propone **qué modelar y qué deliberadamente no**, y deja anotadas las
preguntas que no se pueden contestar sin la cooperativa. Es el proyecto con
más reglas raras del mundo real por metro cuadrado, y modelarlo mal produce
un tablero que dice "todo bien" cuando hay un tipo sin cobertura arriba de un
andamio.

---

## 1. El dominio, tal como lo contó Germán

La cooperativa **no tiene ART**. Los socios no son empleados en relación de
dependencia: son asociados, y su cobertura depende de **seguros personales**
más la póliza que contrata la cooperativa.

La **póliza general es nominal**: cubre a las personas que figuran en su
nómina, no "a la cooperativa". Tienen una **planilla de plantel estable**,
pero **la gente rota entre obras**. Ahí está el agujero de verdad: alguien
entra a una obra y nadie lo agrega a la nómina.

Según el trabajo, además les piden:

- **seguro de caución** — para contrataciones, sobre todo con el Estado
- **seguro contra terceros**
- **coberturas específicas por obra** — trabajo en altura, por ejemplo
- **vehículos** — camión, camioneta
- **ARCA** y **seguros personales** de cada socio

Y son **pólizas de meses**: se caen solas si no se pagan. Germán pidió
explícitamente que **la app avise las red flags**: si está paga o no, cuándo
vencen.

---

## 2. Las dos distinciones que van en el modelo desde el día uno

Si el modelo no arranca con estas dos separadas, después no se arreglan sin
migración.

### 2.a — Vigente ≠ pago

Una póliza **vigente e impaga no cubre**. Son dos dimensiones independientes:

| | Paga | Impaga |
|---|---|---|
| **Dentro de vigencia** | cubre | **NO cubre — el caso peligroso** |
| **Fuera de vigencia** | no cubre | no cubre |

El caso peligroso es el de arriba a la derecha, y es exactamente el que un
solo campo `state` esconde. Un `state` con valores "vigente / vencida /
impaga" obliga a elegir uno cuando la realidad son dos ejes.

**Regla dura:** la app **nunca infiere "pago" de la ausencia de
información**. Si nadie cargó el comprobante, el estado es *sin confirmar*,
no *pago*. Los tres estados honestos del tablero:

- **confirmado con comprobante** — hay un archivo y una fecha
- **sin confirmar** — no sabemos, y lo decimos
- **vencido** — la fecha pasó

### 2.b — Nominal ≠ por obra

Son cardinalidades distintas y no se pueden meter en el mismo campo:

- La **póliza nominal** cubre **una lista de personas**. Cambia cuando cambia
  la lista, no cuando cambia la obra.
- La **póliza por obra o por contratación** (caución, altura, terceros) se
  contrata para **un trabajo**. Cambia cuando cambia el trabajo.
- La **póliza de un bien** (camión, camioneta) cubre **una cosa**, no una
  persona ni una obra.

Tres sujetos asegurados distintos: **persona, obra, bien**. Un solo campo
`tipo` con quince opciones y reglas escondidas en el código es la forma
segura de que dentro de seis meses nadie entienda por qué una alerta no
salta.

---

## 3. Modelo de datos propuesto

### `coop.poliza` — el contrato con la aseguradora

Lo que identifica y ubica la póliza:

- `name` / `numero` — número de póliza
- `aseguradora_id` (`res.partner`)
- `tipo` — general nominal / caución / terceros / altura / vehículo /
  personal del socio / ARCA / otro
- `cobertura` — texto libre: qué cubre y hasta cuánto. **No estructurar esto
  todavía**; ver §5.
- `fecha_inicio`, `fecha_fin` — la vigencia
- `documento` — el PDF. Es respaldo, **no** es el dato.
- `obra_id` — solo para las de obra o contratación
- `equipment_id` / bien asegurado — solo para vehículos y maquinaria
- `member_id` — solo para las personales del socio
- `nomina_ids` → `coop.poliza.nomina`
- `cuota_ids` → `coop.poliza.cuota`

**Lo que NO va como campo suelto:** un booleano `pagada`. El pago vive en las
cuotas, porque la póliza es de meses.

### `coop.poliza.nomina` — quién está cubierto y desde cuándo

Una línea por persona y por período. **No** un `Many2many` plano de socios:
lo que se necesita saber el día del accidente es *si esa persona estaba en la
nómina en esa fecha*, y un many2many solo dice el estado de hoy.

- `poliza_id`, `member_id`
- `fecha_alta`, `fecha_baja`
- `comprobante` — el endoso o la comunicación a la aseguradora

Esto es lo que convierte la nómina en algo auditable. También es lo que
permite contestar "¿estaba cubierto cuando pasó?" seis meses después.

### `coop.poliza.cuota` — la plata, mes a mes

- `poliza_id`, `periodo` (mes), `vencimiento`, `importe`
- `estado`: **confirmado con comprobante / sin confirmar / vencido** — los
  tres de §2.a, calculado, no tipeado a mano
- `comprobante` — el archivo del pago
- `fecha_pago`

### `coop.poliza.requisito` — qué le piden a esta obra

El puente entre la obra y las pólizas. Sin esto no se puede decir *"a esta
obra le falta el seguro de altura"*, solo *"tenemos estas pólizas"*.

- `obra_id`, `tipo_requerido`, `exigido_por` (comitente / municipio / ley),
  `poliza_id` (la que lo satisface, si hay alguna), `fecha_limite`

---

## 4. El cruce — que es *la* función

> **Guardar el PDF es archivo. El cruce es la función.**

La prueba de que este proyecto está terminado no es que el tablero se vea
bien. Es que produce esta frase sola, el mismo día, sin que nadie la busque:

> «Diego López está asignado a Quintriqueo y no figura en la póliza.»

El cruce compara dos conjuntos que ya existen en la app:

- **quién está asignado a una obra activa** → `project.project.socio_obra_ids`
  (ya existe) y quién cargó avances últimamente
- **quién está en la nómina vigente** de la póliza general nominal →
  `coop.poliza.nomina` con `fecha_baja` vacía o futura

La diferencia entre los dos conjuntos es la alerta. Corre diario y también
**en el momento en que se asigna un socio a una obra**, que es cuando la
persona todavía tiene la app abierta y puede hacer algo.

### Qué se rompe si esto se hace mal

Que la app diga que hay cobertura cuando no la hay es **peor que no tener la
app**: reemplaza una preocupación real por una tranquilidad falsa. Ante la
duda, el modelo tiene que decir *no sé*.

---

## 5. Lo que deliberadamente NO se modela (todavía)

Cada campo que no ponemos es una decisión, no un olvido:

- **Las condiciones de cobertura como datos estructurados** (sumas
  aseguradas, franquicias, exclusiones, cláusulas). Es tentador y es una
  trampa: cada aseguradora las escribe distinto, nadie las va a cargar, y
  quedarían vacías dando la impresión de que están consideradas. Van como
  texto y adjunto hasta que alguien las necesite de verdad para algo
  concreto.
- **Cálculo de primas o comparación de aseguradoras.** No es lo que pidieron
  y no es lo que duele.
- **Integración con la aseguradora.** No existe API; el canal real es un
  WhatsApp a un productor.
- **Un modelo propio de vehículos.** El camión y la camioneta pueden vivir en
  `maintenance.equipment`, que ya existe y ya tiene el patrón de
  vencimientos (`service_vencido` con su `search`). Reusarlo, no inventar.

**Regla que ordena todo lo anterior:** *si algo tiene que disparar una alerta,
es un dato; si no, es un adjunto.* La fecha de vencimiento es un dato. La
cláusula 14.3 es un adjunto.

---

## 6. Cuándo y a quién avisa

El riesgo de este proyecto no es técnico, es de calibración. **Una alerta que
llega siempre deja de ser información.** Un tablero que está en rojo todos
los días es un tablero apagado.

Criterio de arranque, para ajustar con uso real:

| Qué | A quién | Cuándo |
|---|---|---|
| Socio asignado a obra y fuera de la nómina | coordinador de esa obra + administración | al asignarlo, y diario mientras siga así |
| Cuota por vencer | administración | una vez, 7 días antes |
| Cuota vencida sin comprobante | administración + consejo | al vencer, y semanal |
| Póliza por vencer | administración | 30 días antes |
| Obra sin un requisito cubierto | coordinador + administración | al crear la obra y al acercarse la fecha límite |

**Lo que NO avisa** —la decisión más importante de la tabla—: nada que la
persona no pueda resolver. Al socio no se le avisa que la cuota está impaga:
no la paga él, y solo genera angustia. Se le avisa a quien puede pagarla.

---

## 7. Preguntas abiertas para Germán — CONTESTADAS 2026-08-25

> [!success] Germán contestó por WhatsApp el 25/08 a las 23:04.
> Las respuestas están transcriptas abajo, textuales, con lo que implican para
> el modelo. **Su numeración no coincide con la de este documento**, así que se
> mapearon por contenido, no por número. Lo que quedó ambiguo está marcado.

### Lo que contestó, y qué define

**1 · Quién carga y mantiene la nómina** — *"Yami de administración manda
planilla al seguro"*.
→ Es **interno**. Yamila, de administración central, arma la planilla y la
manda a la aseguradora. La app **sí** puede darle una pantalla de dos toques, y
la diferencia entre plantel asignado y nómina de la póliza es accionable acá
adentro. No es un tercero al que solo se le puede avisar.

**2 · Qué pasa cuando alguien rota y no está en la póliza** — *"la idea es que
sin seguro NO... A veces como tarda en actualizar hacemos que arranque igual
hasta que salga el trámite pero nosotros asumimos el riesgo"*.
→ **La respuesta más importante de todas.** La regla es bloqueante *por
intención*, pero en la práctica arrancan igual mientras sale el trámite.
Un bloqueo duro se esquivaría por WhatsApp y la app quedaría afuera del
circuito real. El diseño correcto es **bloqueo con excepción registrada**: la
app frena, y si deciden arrancar igual, queda asentado **quién** asumió el
riesgo y **cuándo**. Eso convierte una decisión que hoy es verbal en un
registro — que es exactamente el valor que la app tiene para ofrecer acá.

**3 · ¿Nominal con tope?** — *"sin tope, más asegurados, más pagas"*.
→ Nominal, **sin límite de cabezas**. Agregar a alguien siempre se puede; lo
que cambia es la plata. No hace falta modelar aprobación por cupo.

**4 · Frecuencia** — *"Mensual o más.. 3 meses"*, aclarado el 25/08:
*"si se suma alguien se pide actualización de listas, no solemos rotar mucho x
ahora sino es al plazo de la póliza puede ser 3, o 6 meses"*.

→ **RESUELTO, y cambia el diseño de los avisos para mejor.** Son dos cosas
distintas:

- **La nómina se actualiza por EVENTO, no por calendario.** El disparador es
  "se sumó alguien" → se pide actualización de listas. No hay un día del mes en
  que se revisa. Eso encaja con el cruce diario plantel-vs-póliza que ya
  propone §4: el evento que importa es una asignación, y el cruce lo detecta al
  día siguiente sin depender de que alguien se acuerde.
- **El plazo de la póliza es de 3 o 6 meses.** Con esos plazos, avisar a
  30/15/7 días es holgado y no empapela.

⚠️ **"no solemos rotar mucho *por ahora*"** — el "por ahora" es la parte
importante. El diseño no puede apoyarse en que la rotación sea baja: el cruce
diario cuesta lo mismo con 6 socios que con 60, así que se hace igual.

**5 · Seguros personales del socio** — *"nosotros adm central Yamila"*.
→ Los **controla la cooperativa**, no cada socio por su cuenta. Entran al
modelo con el mismo peso que la póliza general y sí generan alertas.

**6 · Quién es "administración"** — *"adm central Yamila"*.
→ Administración central, Yamila. **Falta un rol en la app**: hoy hay
coordinador, socio, síndico y manager, y el que paga y mantiene las pólizas no
es ninguno de esos con precisión. Es una decisión de permisos, no de dominio.

### Y de yapa, la pregunta de P2 (documentos encadenados)

**El contrato con el cliente, ¿adjunto o fuente de los hitos?** — *"las dos
cosas se guarda para archivo y define monto total, y condiciones, puede ser
fraccionado en meses ese monto, salen fechas para la ruta crítica, tiempo de
entrega x ejemplo. Pero los montos de la certificación tienen que ver con el
trabajo real realizado, el avance"*.

→ **Las dos cosas, pero con un corte limpio:**
- Del contrato salen **el monto total, las condiciones y las FECHAS** — y esas
  fechas alimentan la ruta crítica (plazo de entrega).
- Los **montos de certificación NO salen del contrato**: salen del **avance
  real medido**.

Esto es una muy buena noticia para P2: **no se convierte en otro proyecto
entero**. La app ya calcula la certificación desde la foja y el avance, que es
justo lo que Germán describe. Lo que hay que agregar es que el contrato aporte
**plazos** al CPM, no montos.

---

## 7b. Lo que sigue sin contestar

⚠️ **Una contradicción con lo anotado el 24/08, que conviene despejar** — no
bloquea el modelo, pero sí el texto de los avisos.

`Pedidos-German-2026-08-24.md §9b` dice **"las pólizas son mensuales"**. El
25/08 Germán dice que el plazo es de **3 o 6 meses**.

La lectura que reconcilia las dos —y que es lo habitual acá— es que el **plazo**
de la póliza sea de 3 a 6 meses y la **prima se pague en cuotas mensuales**. Eso
deja intacto lo importante de §9b, que no era el plazo sino que *una póliza
vigente e impaga no cubre*: se sigue cayendo sola cada mes si no se paga la
cuota, aunque el plazo sea semestral.

**Es una lectura, no un dato confirmado.** El modelo la soporta sin cambios
porque vigencia y pago ya son dos ejes separados; lo que cambia si me equivoco
es cada cuánto se pide el comprobante de pago. Confirmarlo antes de escribir el
calendario de avisos de pago.


1. **¿Quién carga y mantiene la nómina de la póliza?** Si es una persona en
   administración, la app le tiene que dar una pantalla de dos toques. Si es
   el productor de seguros por afuera, la app solo puede *avisar la
   diferencia*, no arreglarla — y el diseño cambia entero.
2. **¿Con qué frecuencia real cambia la nómina?** Si es semanal, la
   comunicación a la aseguradora es parte del flujo. Si es mensual, alcanza
   con un aviso.
3. **La póliza general, ¿es por cantidad de personas o por lista de nombres?**
   Germán dijo nominal, pero conviene confirmar si hay un tope de cabezas: si
   lo hay, agregar a alguien puede requerir aprobación y plata.
4. **¿Qué pasa hoy cuando alguien rota a una obra y no está en la póliza?**
   ¿Trabaja igual? ¿Se frena? La respuesta define si la alerta es informativa
   o **bloqueante**, y eso es una decisión de ellos, no nuestra.
5. **Los seguros personales del socio: ¿los controla la cooperativa o son
   asunto de cada uno?** Si la cooperativa los controla, entran al modelo con
   el mismo peso que la póliza general. Si no, son un dato de referencia y no
   deberían generar alertas a nadie.
6. **¿Quién es "administración"?** Hoy la app tiene coordinador, socio,
   síndico y manager. Si el que paga las pólizas no es ninguno de esos, falta
   un rol.

---

## 8. Cómo se implementa después de esta pasada

Esta especificación es la parte cara. Una vez respondidas las preguntas de
§7, la implementación es mecánica y se puede hacer con modelo barato:

1. Los cuatro modelos de §3, con sus ACL.
2. El cómputo del estado de cuota (los tres estados honestos).
3. El cruce de §4 como método buscable, más su alerta.
4. El tablero de vencimientos: una lista ordenada por urgencia, no un
   dashboard con gráficos.
5. La pantalla de nómina, pensada para dos toques.

**Orden sugerido:** primero el cruce, aunque el tablero no exista. El cruce es
lo que salva a alguien; el tablero es lo que se ve lindo en la demo.
