# CoopeApp — Informe CEO: piloto, relación comercial y estado real
**2026-06-09 · Basado en: repo completo (5 módulos verificados), vault de Obsidian (01-Projects/coopeapp, decisions-log, dailies)**

---

## 1. Opinión honesta de CEO

**CoopeApp es tu único proyecto con demanda real esperando — y lo estás dejando enfriar.**

Mirá el contraste con el resto del portfolio: Descanso y Starlit tienen producto y cero audiencia; Oficio tiene código y cero prestadores. CoopeApp tiene **52 cooperativas interesadas, 7 piloto en Neuquén, un canal de distribución (Juan + el síndico de la Federación) y una cooperativa ya probando la app**. Es el único proyecto donde hay una persona del otro lado a la que le importa el resultado — tu propio vault lo dice.

Y sin embargo: la reunión con Juan del 30 de abril **nunca ocurrió** (cirugía, viaje — razones válidas), el proyecto quedó congelado el 14 de mayo "hasta después del Mundial", y hoy van **~6 semanas de silencio comercial**. El riesgo de CoopeApp no es técnico — es que Juan y la Federación pierdan la fe mientras vos no aparecés.

Decisiones que te debo como CEO:

1. **Congelar el código está bien. Congelar la relación, no.** No hace falta viaje ni sprint: un mensaje a Juan **hoy** (5 minutos): "estoy saliendo de la cirugía, el proyecto sigue, te propongo videollamada de 30 min la semana del X para mostrarte lo que ya funciona en el servidor". Eso compra 6 semanas más de paciencia y no compite con el Mundial ni con Descanso.
2. **Esto no necesita campaña de marketing — necesita un piloto que funcione.** B2B con canal de federación: el go-to-market es 1 cooperativa de construcción usando liquidaciones y asambleas en serio durante 60 días, con vos documentando el caso. Las otras 51 se venden con ese caso, no con contenido.
3. **Definí el precio antes de la reunión, no después.** Hoy no hay modelo de cobro en ningún lado. Propuesta para validar con Juan: piloto gratis 90 días → ARS por socio activo/mes (ej. $2.000-3.000/socio/mes, mínimo $80-100k/coop) o tarifa plana por cooperativa. La Federación puede ser el canal de cobro/aval. Que el piloto firme una carta de intención con precio, aunque no pague todavía.
4. **El bloqueante técnico real para confiarle nómina a alguien no es features: son los backups.** Hoy el VPS no tiene estrategia de backup documentada. Si se pierde una liquidación de una cooperativa real, el proyecto muere por confianza, no por código.
5. **Encaje en el portfolio:** mensaje a Juan hoy + videollamada esta quincena (2 h total). El sprint técnico del handoff (~2-3 días) va **después** del sprint Mundial de WCF, idealmente fines de junio, antes del lanzamiento de Descanso en julio. CoopeApp es trabajo por ventanas — pero las ventanas de relación no se negocian.

**Veredicto: GO, con la relación primero.** Es posiblemente tu proyecto con mejor ratio demanda/esfuerzo — sería una ironía que el único con clientes esperando muera por inanición de agenda.

---

## 2. Estado técnico — verificado en disco

### Lo que hay (mejor de lo documentado)
- **5 módulos** (CLAUDE.md documenta 4 — `coop_books` existe y no figura): coop_members (392 LOC), coop_payroll (508), coop_assembly (318), coop_books (289), coop_construction (188). ~1.700 LOC Python idiomático Odoo (models.Model, vistas XML, 5 `ir.model.access.csv` ✅).
- 8 archivos de tests (members/payroll/assembly/books). Reportes QWeb con contenido real (84/66 líneas — la auditoría automática que los dio por vacíos era falsa alarma).
- Sin credenciales en archivos trackeados ✅ (los matches de "secret" eran "secretario" y "voto secreto"). La IP del VPS en CLAUDE.md es aceptable en repo privado.
- Git limpio salvo `scripts/load_demo_data.py` sin trackear y un `.git/index.lock` huérfano.

### Lo que falta para un piloto en serio (por severidad)
| Sev. | Qué | Detalle |
|---|---|---|
| 🔴 | **Backups del VPS** | Sin pg_dump programado ni copia offsite ni prueba de restore documentada. Bloqueante para datos de nómina reales |
| 🔴 | **Infra como código** | No hay docker-compose ni runbook en el repo — todo vive solo en el VPS (178.105.15.189). Sos single point of failure |
| 🟠 | **Localización argentina desactivada** | "Pendiente de fix" desde hace semanas. Scope a definir: ¿hace falta para liquidaciones cooperativas (que no son nómina en relación de dependencia) o solo para facturación? No arreglar de más |
| 🟠 | **Separación por cooperativa** | 7 pilotos no pueden compartir una DB. La respuesta NO es multi-tenancy custom: es el estándar Odoo de **una database por cooperativa** (`coop_<slug>` + dbfilter). Barato y suficiente |
| 🟠 | **coop_construction incompleto** | El vertical de arranque: certificados de avance a medio hacer, work_entry sin validaciones, **0 tests**. Completar solo lo que el piloto necesite |
| 🟡 | CI inexistente | 8 archivos de test que solo corren a mano. Un GitHub Action con `--test-enable` alcanza |
| 🟡 | Doc drift | CLAUDE.md: dice repo en `~/Documents/coopeapp` (está en `~/Dev/coopeapp`) y omite coop_books |

---

## 3. Plan — piloto antes que producto (sin marketing tradicional)

### Esta semana (no compite con el Mundial — 2 h total)
1. **Mensaje a Juan hoy.** Reanclar la relación: videollamada 30 min semana próxima, demo en vivo del VPS (socios + liquidación + asamblea con voto). Sin viaje.
2. Preparar la agenda de esa reunión (el template del vault del 30/4 quedó vacío — ahora se llena): alcance del piloto, precio propuesto, qué necesita él de la Federación, criterios de éxito del piloto.

### Reunión con Juan (objetivos de salida)
- 1 cooperativa de construcción elegida como piloto #1 (de las 7).
- Carta de intención con precio (gratis 90 días → tarifa definida).
- Compromiso de la Federación: aval + canal a las 52.
- Fecha de onboarding (post 19/7, cuando termine el sprint Mundial).

### Sprint técnico (fines de junio, 2-3 días — handoff a Claude Code)
- Backups + runbook + compose al repo, una DB por coop, completar coop_construction al alcance del piloto, diagnóstico de localización AR. (Detalle en la nota de fixes del vault.)

### Piloto (agosto-septiembre, 60 días)
- 1 coop usando socios + liquidaciones + asambleas reales. Vos como soporte directo (WhatsApp). Documentar TODO: el caso de éxito es el material de venta a las otras 51.
- Métrica de éxito: la coop hace su liquidación mensual completa en CoopeApp 2 meses seguidos + el consejo aprueba un acta generada por el sistema.
- Kill criteria: si el piloto no adopta en 60 días con soporte directo, el problema es producto/proceso — parar y rediseñar antes de sumar coops.

### Escala (octubre+)
- Caso documentado → presentación a la Federación → onboarding por tandas de 2-3 coops. Precio validado. Recién ahí pensar en marketing (que en este negocio es: el síndico contando el caso).

---

## Próximos 7 días
1. Hoy: mensaje a Juan (5 min). Lo único urgente de verdad.
2. Esta semana: agenda de reunión + propuesta de precio en una página.
3. Esta semana: handoff técnico anotado para Claude Code (no ejecutar hasta post-sprint Mundial, salvo backups si hay datos reales ya cargados — eso sí es ya).
4. Verificar con Juan si la cooperativa que "está probando" cargó datos reales — si sí, los backups suben a HOY.
