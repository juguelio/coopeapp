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

Barra inferior común: **Inicio · Cargar · Mi plata · Obra** (el contenido de
"Inicio" cambia según el rol).

### Socio (el 80% de los usuarios)
- **Inicio:** saludo, su obra y tarea de hoy, botón gigante "CARGAR LO QUE HICE",
  estado del último avance (✓ validado / ⏳ esperando al capataz).
- **Cargar (wizard 3 pasos):**
  1. ¿En qué trabajaste? → tarjetas con los ítems de su tarea/foja
  2. ¿Cuánto hiciste? → número grande + unidad del ítem (m², ml…) con +/-
  3. ¿Cuánto trabajo te llevó? → jornal / horas / tarea + cantidad → Confirmar
- **Mi plata:** participación, avances validados del mes, productividad simple
  ("hiciste 45 m² en 3 jornales"), liquidación.
- **Obra:** avance físico (barra grande), etapa en curso, transparencia: lo que
  ve el socio es lo mismo que ve el manager (principio ACI).

### Capataz
- Inicio = socio + tarjeta "Tenés N avances para revisar".
- **Validar:** lista de tarjetas (quién, qué, cuánto) con dos botones gigantes
  ✓ Está bien / ✗ Corregir. Una por una, estilo bandeja.

### Manager / Presidente
- **Inicio = tablero:** 3 números grandes (avance físico %, saldo sin planificar,
  controlador) con semáforo + tareas críticas atrasadas en rojo.
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

## Fases

| Fase | Qué | Criterio de éxito |
|------|-----|-------------------|
| 1 | Validar mockup con Juan + 2-3 socios | Socio carga un avance sin ayuda al primer intento |
| 2 | `coop_portal`: login PIN, home socio, wizard cargar, mi plata, obra | Socios del piloto cargan avances reales una semana seguida |
| 3 | Capataz validar + tablero manager/síndico | El capataz valida desde el celular; Juan mira el tablero |
| 4 | PWA completa: instalable, offline con cola de sync | Carga funciona sin señal en obra |
| 5 | Gantt visual propio (OWL) sobre los campos CPM | Hoja de ruta visual en el tablero |

## Qué NO va en la app de socios

Configuración, foja completa editable, proyecciones editables, reportes,
usuarios. Todo eso es backoffice y ya existe en Odoo. Cada cosa que se agrega
acá tiene que pasar el filtro: *¿un socio que apenas usa WhatsApp lo necesita
todas las semanas?* Si no, va al backend.
