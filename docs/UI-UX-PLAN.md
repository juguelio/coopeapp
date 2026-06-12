# Plan UI/UX — App de socios (coopeapp)

**Fecha:** 2026-06-12 · **Estado:** propuesta para validar con Juan y socios piloto
**Mockup navegable:** `docs/mockup-ui-socios.html` (abrir en el celular o achicar la ventana)

## El problema

El backend de Odoo es para administrativos. Los socios de obra son gente que apenas
usa WhatsApp: menús anidados, tablas de 12 columnas, filtros y breadcrumbs los
expulsan. Si cargar un avance cuesta más que mandar un audio, no lo van a hacer,
y sin carga diaria no hay % productivo, no hay foja al día y no hay confianza.

## Principio rector

**La app del socio no es Odoo simplificado: es otra app.** Odoo backend queda como
backoffice. Los socios (y también capataz, manager y síndico en el día a día) usan
una interfaz propia, mobile-first, servida por el mismo Odoo.

## Decisiones tomadas

- **Arquitectura:** portal Odoo + PWA. Módulo nuevo `coop_portal` con controllers
  HTTP en `/app`, templates QWeb propios (CSS propio, cero dependencia del
  webclient), manifest PWA para instalarla como ícono en el celular. Misma DB,
  mismo login, mismo deploy.
- **Alcance:** todos los roles usan la UI simple. Cada rol ve una home distinta,
  no más opciones.
- **Validación:** mockup clickeable antes de codear. Probarlo con 2-3 socios
  reales de la coop piloto: si no pueden cargar un avance sin ayuda en el primer
  intento, se rediseña.

## Reglas de diseño (no negociables)

1. **Una acción por pantalla.** Nunca dos preguntas juntas. Los flujos son
   wizards de un dato por paso.
2. **Cero menús.** Navegación = barra inferior con máximo 4 botones (ícono +
   palabra). Todo lo importante a 2 toques o menos.
3. **Lenguaje de obra, no de software.** "¿Qué hiciste hoy?" en vez de "Crear
   registro de avance de medición". "Mi plata" en vez de "Liquidaciones".
4. **Botones gigantes** (mínimo 56px de alto), una mano, pulgar. Nada de íconos
   solos: siempre ícono + texto.
5. **Números grandes y semáforos.** Barras de progreso y verde/amarillo/rojo en
   vez de tablas. Las tablas viven en Odoo backend.
6. **Confirmación visible y deshacer.** Después de cargar: pantalla verde con
   check gigante y "lo va a revisar el capataz". Botón corregir.
7. **Login sin password:** teléfono + PIN de 4 dígitos. Sesión larga (no pedir
   login cada vez).
8. **Tolerante a la mala señal.** La carga de avance guarda local (localStorage/
   IndexedDB) y sincroniza cuando hay red. Las obras no tienen buena señal.
9. **WhatsApp como referencia mental:** listas de tarjetas, un botón de acción
   principal por pantalla, scroll vertical simple.

## Pantallas por rol

**La barra inferior es por rol** — son "las 4 cosas que hacés todos los días",
y el día de un socio no se parece al de un coordinador ni al del administrador.
Siempre 4 botones, siempre Inicio primero:

| Rol | Función del rol | Barra |
|-----|-----------------|-------|
| Socio | produce y cobra | Inicio · **Cargar** · Mi plata · Obra |
| Coordinador | revisa y abastece | Inicio · **Avances** (validar) · Pedidos · Corralón |
| Administrador | decide y presupuesta | Inicio · **Ruta** (crítica) · OTs · Materiales |
| Síndico | fiscaliza | Inicio · **Ruta** · Asamblea (actas) · Economía |

En negrita la acción nº1 de cada rol. Lo episódico (asamblea para el socio,
relevamiento asignado) sigue entrando como tarjeta en Inicio, no como botón.

### Socio (el 80% de los usuarios)
- **Inicio:** saludo, su obra y tarea de hoy, botón gigante "CARGAR LO QUE HICE",
  estado del último avance (✓ validado / ⏳ esperando al coordinador).
- **Cargar (wizard 3 pasos):**
  1. ¿En qué trabajaste? → tarjetas con los ítems de su tarea/foja
  2. ¿Cuánto hiciste? → número grande + unidad del ítem (m², ml…) con +/-
  3. ¿Cuánto trabajo te llevó? → jornal / horas / tarea + cantidad → Confirmar
- **Mi plata:** participación, avances validados del mes, productividad simple
  ("hiciste 45 m² en 3 jornales"), liquidación.
- **Obra:** avance físico (barra grande), etapa en curso, transparencia: lo que
  ve el socio es lo mismo que ve el manager (principio ACI). Además:
  - **Aceptar trabajo asignado:** tarjeta con la tarea propuesta (qué, cuándo,
    con quién) y dos botones: ✓ Acepto / No puedo (avisa al coordinador para
    reasignar).
  - **Pedir materiales** (wizard 2 pasos): ¿qué necesitás? → catálogo de lo más
    común (cemento ×bolsa 50kg, cal ×bolsa 25kg, arena ×m³, ladrillo hueco ×u,
    hierro 8mm ×barra, pintura látex ×lata 20L, "otro") → ¿cuánto? → pedir.
    El pedido sube al coordinador; el socio ve el estado de sus pedidos
    (⏳ en revisión / ✓ en la orden / ✗ rechazado).

### Coordinador (antes "capataz") — puede gestionar varias obras
- Inicio con **selector de obra** (chips arriba: las obras a su cargo); todo lo
  de abajo (avances, pedidos, orden al corralón) es de la obra seleccionada.
- Tarjeta "Tenés N avances para revisar" + tarjeta "N pedidos de materiales
  esperando" por obra.
- **Validar avances:** lista de tarjetas (quién, qué, cuánto) con dos botones
  gigantes ✓ Está bien / ✗ Corregir. Una por una, estilo bandeja.
- **Revisar pedidos de materiales:** por pedido, ✓ Aceptar / ✗ Rechazar /
  ✏️ Corregir cantidad. Lo aceptado se acumula en la orden.
- **Orden al corralón:** consolidado de pedidos aceptados → vista previa del
  mensaje → botón WhatsApp (`wa.me` con texto prearmado) o SMS. El coordinador
  solo toca "enviar": no redacta nada.

### Administrador (antes "Manager") — máxima información, cero operativa
- **NO valida avances ni pedidos** — eso es del coordinador. Su trabajo:
  visión total, decisiones, presupuestos.
- **Inicio = administración multi-obra:**
  1. **Ruta crítica primero** (es su vista principal): alertas de todas las
     obras con holgura 0, atrasos y el **cambio** ("recalculada hoy: fin de
     Quintriqueo +2 días"). Vista detallada por obra: cadena crítica con
     fechas, responsable y causa del atraso.
  2. Órdenes de trabajo por estado (presupuestar / relevando / aprobada sin
     coordinador).
  3. **Cartera de obras:** una tarjeta por obra con avance %, saldo sin
     planificar y controlador con semáforo, y quién la coordina.
  4. **Materiales y precios** (la base del presupuesto): saldos de acopio,
     listas vigentes y alertas de precio viejo.
- Al aprobarse una OT: **crea la obra y elige el coordinador** (viendo cuántas
  obras tiene cada uno a cargo). La obra le aparece al coordinador en su app.
- Acceso a validar, etapas y hoja de ruta simplificada (lista, no Gantt).
- Para todo lo demás: botón "Ir al sistema completo" (Odoo backend).

### Síndico (Juan)
- Tablero de manager en **solo lectura** + sección "Certificaciones" (fase
  posterior: firma digital).

## Arquitectura técnica

```
coop_portal (módulo nuevo, depende de coop_construction)
├── controllers/portal.py      # rutas /app/* (http.Controller, auth='user')
├── views/portal_templates.xml # QWeb: layout + una plantilla por pantalla
├── static/src/css/app.css     # design system propio (variables, botones, cards)
├── static/src/js/app.js       # vanilla JS: wizard, guardado offline, sync
├── static/manifest.json       # PWA: nombre, ícono, standalone
└── static/sw.js               # service worker: cache + cola de avances offline
```

- Los socios son usuarios internos con grupo `group_coop_member` (ya existe);
  el controller enruta por grupo a la home correspondiente.
- Sin framework JS: QWeb server-side + JS vanilla. Menos piezas, carga rápida
  en celulares viejos. OWL solo si una pantalla lo exige (el Gantt, fase 5).
- Datos: los modelos ya existen (`coop.avance.medicion`, `coop.foja.item`,
  `coop.etapa`, CPM en `project.task`). El portal solo lee y crea avances.

## Cobertura de todos los módulos

La app del socio es **una sola** y cubre toda la plataforma. La barra inferior
no crece nunca: lo episódico (una asamblea, una liquidación nueva) aparece como
tarjeta en Inicio cuando corresponde, no como menú permanente.

| Módulo | Qué usa el socio | Dónde vive en la app |
|--------|------------------|----------------------|
| coop_construction | Cargar avance, ver obra, ruta crítica | **Cargar** + **Obra** (ya en mockup) |
| coop_payroll | Liquidaciones, anticipos, participación | **Mi plata** (ya en mockup) |
| coop_members | Mis datos, mis aportes, capital social | **Mi plata** → "Mis aportes" |
| coop_assembly | Convocatoria, **votar**, actas | Tarjeta en **Inicio** cuando hay asamblea activa + pantalla de voto (sí/no/abstención con botones gigantes) |
| coop_books | Libros contables | Backoffice. Al socio le llega solo el resumen de transparencia en **Obra**/**Mi plata** |

El voto de asamblea es prioridad alta dentro de esto: es participación ACI y es
el caso de uso más simple de todos (una pregunta, tres botones).

**Y el backend de Odoo:** no va a ser nunca así de navegable, y no importa.
Queda para los 2-3 administrativos que hacen carga masiva, configuración,
contabilidad y reportes. La regla es: si lo hace un socio o se hace parado en
la obra, va en la app; si se hace sentado en un escritorio una vez al mes, queda
en Odoo.

## Ruta crítica editable — carriles por oficio

**Principio:** el grafo de dependencias se arma **por oficio** (albañilería,
electricidad, sanitaria, terminaciones… — ya existe `categoria_tarea` en las
tareas). Cada oficio es un carril que avanza en paralelo; las dependencias
**entre** oficios se cargan solo donde la dependencia es física real (el
electricista no cablea sin mampostería, pero zanjea y arma tablero sin
esperar a nadie). Resultado: el incumplimiento de un albañil corre **su
cadena** y los cruces declarados — nada más. El electricista ni se entera,
y el sistema lo dice explícitamente ("Electricidad: no afectada").

**El Administrador edita la ruta** desde la app (es el único que puede):
- Por tarea: duración (días), oficio, cuadrilla asignada y **de qué depende**
  (selector de tareas previas).
- Al guardar, el CPM recalcula solo (el motor ya está deployado y acepta
  cualquier grafo; los ciclos ya se bloquean con error claro).
- **Aviso anti-cadena-falsa:** si crea una dependencia entre oficios distintos,
  la app pregunta "¿Electricidad realmente necesita que termine Pintura?" —
  la dependencia floja es lo que hace que un atraso contagie a todos.
- Cada recálculo muestra el **impacto diferencial**: qué carril se corre,
  cuántos días, y qué carriles quedan intactos. Eso es lo que el admin ve en
  su vista de Ruta ("fin de Quintriqueo +2 días · Electricidad sin cambios").

Coordinador y socios ven la ruta (lectura); el socio ve solo lo suyo: su
próxima tarea, desde cuándo, y si está en cadena crítica.

## Reportes del Administrador

**Problema:** las operaciones viven en 6+ modelos distintos (avances, pedidos,
órdenes al corralón, gastos de etapa, retiros de acopio, certificados). El
admin necesita verlas como **una sola línea de tiempo filtrable**.

**Backend — `coop.operacion` (vista SQL, no tabla):** modelo Odoo con
`_auto = False` montado sobre un `UNION ALL` de las operaciones existentes,
normalizadas a: `fecha`, `tipo` (avance / pedido / orden / gasto / retiro /
certificado / asamblea), `member_id` (quién), `obra_id`, `descripcion`,
`monto`, `referencia` (link al registro original). Cero duplicación de datos:
es una vista, siempre al día.

Con eso el **backend de Odoo regala todo lo demás**: filtros por rango de
fecha, agrupar por día/semana/mes/socio/obra/tipo, vista pivot, búsqueda por
nombre y **export a Excel nativo**. Para reportes pesados, el admin va ahí.

**En la app — pantalla "Reportes"** (tarjeta en el Inicio del admin):
- Rango: chips Hoy / 7 días / Mes / Elegir fechas.
- Filtros: tipo de operación (chips), obra, y buscador por nombre.
- Lista cronológica (quién, qué, cuánto, en qué obra) + totales del período
  arriba (operaciones, $ gastado, m² avanzados).
- Botones "Excel" y "PDF" → el mismo filtro aplicado, generado por Odoo
  (reporte QWeb / xlsx) y descargado al teléfono.
- Síndico: misma pantalla, solo lectura (fiscalización con filtros).

## Pedidos de materiales — backend

El loop completo: socio pide desde la obra → coordinador acepta/corrige/rechaza
→ orden consolidada → WhatsApp/SMS al corralón.

- **`coop.material`** (catálogo): nombre, unidad de compra (bolsa 50kg, m³,
  unidad, barra, lata…), ícono. Precargado con los 6-8 más comunes; el manager
  agrega los del rubro de cada obra.
- **`coop.pedido.material`**: obra_id, member_id (quien pide), material_id (u
  "otro" con texto libre), cantidad, nota, estado:
  `pendiente → aceptado / rechazado` (+ `editado` con cantidad original
  preservada para trazabilidad — el socio ve qué le corrigieron y por qué).
- **`coop.orden.corralon`**: obra_id, corralon_id (res.partner proveedor con
  teléfono), pedido_ids aceptados, estado `borrador → enviada → confirmada →
  entregada`. `mensaje` generado por plantilla (cooperativa, obra, ítems
  agrupados por material, firma del coordinador).
- **Envío v1: `wa.me/<tel>?text=<mensaje>`** — abre WhatsApp del coordinador
  con el texto armado; él solo aprieta enviar. Cero costo, cero API, funciona
  con el corralón de siempre. `sms:` como alternativa. La orden queda
  registrada en la app igual (estado `enviada` + timestamp).
- **v2 (si el volumen lo pide):** WhatsApp Business API para envío automático
  y confirmación del corralón por el mismo canal.
- Permisos: socio crea pedidos y ve los suyos; coordinador (nuevo grupo
  `group_coop_coordinador`, entre member y manager) gestiona pedidos y órdenes
  de sus obras; transparencia de lectura para todos como siempre.
- Al marcar la orden `entregada`, los ítems quedan disponibles para imputarse
  como gasto real del rubro Materiales en la etapa (cruce con
  `coop.proyeccion.gasto` — cierra el control de uso y de pedido).

## Fases

| Fase | Qué | Criterio de éxito |
|------|-----|-------------------|
| 1 | Validar mockup con Juan + 2-3 socios | Socio carga un avance sin ayuda al primer intento |
| 2 | `coop_portal`: login PIN, home socio, wizard cargar, mi plata, obra (aceptar trabajo + pedir materiales) | Socios del piloto cargan avances y pedidos reales una semana seguida |
| 3 | Coordinador: validar avances + pedidos + orden al corralón (wa.me) + tablero manager/síndico | El coordinador manda una orden real al corralón desde la app |
| 4 | PWA completa: instalable, offline con cola de sync | Carga funciona sin señal en obra |
| 5 | Gantt visual propio (OWL) sobre los campos CPM | Hoja de ruta visual en el tablero |

## Qué NO va en la app de socios

Configuración, foja completa editable, proyecciones editables, reportes,
usuarios. Todo eso es backoffice y ya existe en Odoo. Cada cosa que se agrega
acá tiene que pasar el filtro: *¿un socio que apenas usa WhatsApp lo necesita
todas las semanas?* Si no, va al backend.
