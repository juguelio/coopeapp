# Limpieza y branding del backoffice (Odoo /web)

El backoffice de Odoo se siente "viejo" y lleno de menús que la coop no usa.
Esto lo afecta solo a los **administradores** (los socios solo ven `/app`, que
ya es moderno). Plan en 4 pasos, de mayor a menor impacto.

## 1. `web_responsive` (OCA) — moderniza el shell (gratis)

Es el cambio que más se nota: cajón de apps en grilla, buscador con comando
(Ctrl+K), barra pegajosa, usable en celular.

En el VPS:
```bash
ssh coopeapp-vps
cd ~/odoo-coop/addons
git clone --depth 1 -b 18.0 https://github.com/OCA/web.git oca-web
```
El `addons_path` de Odoo tiene que incluir `~/odoo-coop/addons/oca-web` (revisá
el `docker-compose.yml` / variable de entorno; si no lo toma, agregá esa carpeta
al path o mové `web_responsive` y sus dependencias a `~/odoo-coop/addons/`).
Después:
```bash
cd ~/odoo-coop
docker compose run --rm odoo odoo -i web_responsive -d coop_piloto --stop-after-init
docker compose restart odoo
```

## 2. `coop_ui` — branding coopeapp (este repo)

Módulo nuevo en `addons/coop_ui`: pinta el backoffice y el login de verde
coopeapp, esconde "Powered by Odoo" / gestor de bases / links de soporte.
Se deploya como cualquier módulo:
```bash
./scripts/deploy.sh coop_ui   # o el auto-deploy al push
```
**El logo:** subilo una vez en Ajustes → Compañías → tu cooperativa → logo. Odoo
lo usa solo en el login, los PDFs y el menú. El favicon: misma pantalla (campo
favicon) o se hereda del logo.

## 3. Desinstalar apps que no se usan

En **Apps → (quitar filtro "Apps") → Instaladas**, desinstalá lo que esté de más.

**NO tocar (las necesita coopeapp):** Facturación/Contabilidad (`account`,
la usa coop_books), Proyecto (`project`), Mantenimiento (`maintenance`),
Conversaciones (`mail`), Contactos (útil), y todos los `Cooperativa - *`.

**Seguras de desinstalar si aparecen y no las usás:** Sitio web / eCommerce,
CRM, Ventas, Compras, Inventario (si no lo usás), Email Marketing, Live Chat,
Eventos, Encuestas, Punto de Venta, Fabricación. (Desinstalá de a una y revisá
que todo siga abriendo.)

## 4. Usuarios admin sin menús técnicos

Para que el admin vea un backoffice limpio:
- Que esté en **Administrador Cooperativo** (`group_coop_manager`) — ya implica
  Coordinador, Socio y Proyecto.
- Que **NO** tenga "Ajustes" / "Administración: Settings" (`base.group_system`)
  salvo Juguelio. Sin ese grupo no ve Ajustes, Apps ni menús técnicos.
- Modo desarrollador **apagado** para los admins (Ajustes → Desactivar modo
  desarrollador). Solo Juguelio lo prende cuando hace falta.

## Nota honesta
Odoo Community no va a verse como un SaaS nuevo ni con todo esto — el theme
realmente moderno es el de Enterprise (se paga por usuario, no vale para 2-3
admins). Pero `web_responsive` + verde coopeapp + menos menús lo dejan limpio,
en tu marca y para nada "dated".
