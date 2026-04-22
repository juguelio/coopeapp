# coopeapp

Plataforma de gestión integral para cooperativas de trabajo, construida sobre Odoo 18 Community.

Diseñada desde los 7 principios cooperativos de la Alianza Cooperativa Internacional (ACI), no como un ERP empresarial adaptado sino como una herramienta cooperativa por arquitectura.

## Estado actual

MVP en desarrollo. 4 módulos funcionando en producción con cooperativa piloto en Neuquén, Argentina.

## Módulos

| Módulo | Descripción | Estado |
|--------|-------------|--------|
| `coop_members` | Socios: altas, bajas, aportes, capital social | ✅ Producción |
| `coop_payroll` | Liquidaciones transparentes con conformidad del socio | ✅ Producción |
| `coop_assembly` | Asambleas, votaciones y actas automáticas | ✅ Producción |
| `coop_books` | Libros cooperativos para INAES/IPCyMER | ✅ Producción |
| `coop_construction` | Obras, Gantt, materiales, corralón, certificaciones | 🔄 En desarrollo |

## Principios cooperativos aplicados

Cada módulo implementa los principios ACI de forma concreta:

- **Control democrático**: asambleas con quórum automático, votaciones con 4 tipos de mayoría, actas generadas automáticamente
- **Transparencia**: cada socio ve su propia liquidación antes de que se pague, puede marcar observaciones y dar conformidad
- **Participación económica**: aportes, retiros y capital social visibles para cada socio
- **Autonomía**: código abierto, exportación libre de datos, sin vendor lock-in

## Stack técnico

- **Odoo 18 Community** — base ERP
- **Python 3.11** — módulos cooperativos
- **PostgreSQL 16** — base de datos
- **Docker Compose** — orquestación
- **VPS Hetzner** — infraestructura

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/tuusuario/coopeapp.git
cd coopeapp

# Configurar credenciales
cp config/odoo.conf.example config/odoo.conf
# Editar config/odoo.conf con tus credenciales

# Levantar
docker compose up -d

# Instalar módulos
docker compose run --rm odoo odoo -i coop_members,coop_payroll,coop_assembly,coop_books -d tu_db --stop-after-init
```

## Deploy al VPS

```bash
# Subir módulo al servidor
scp -r addons/MODULO/ odoo-admin@TU-IP:~/odoo-coop/addons/

# Actualizar en producción
ssh odoo-admin@TU-IP "cd ~/odoo-coop && docker compose run --rm odoo odoo -u MODULO -d coop_piloto --stop-after-init && docker compose up -d"
```

## Contexto

Proyecto iniciado en abril 2026 con el respaldo del síndico de la Federación de Cooperativas de Neuquén. 52 cooperativas interesadas, 7 cooperativas piloto en Neuquén en distintos rubros.

## Licencia

AGPL-3.0 — coherente con el principio cooperativo de autonomía e independencia.

## Contacto

joaquin.apostolo@gmail.com
