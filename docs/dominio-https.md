# Dominio + HTTPS — coopeapp.com.ar

Objetivo: servir `https://coopeapp.com.ar/app/ingresar` con certificado válido,
en vez de `http://178.105.15.189:8069`.

- **Dominio:** coopeapp.com.ar (NIC.ar, delegado a Cloudflare)
- **VPS:** 178.105.15.189 (Hetzner). Odoo en docker, puerto 8069 publicado.
- **Proxy elegido:** Caddy nativo en el host (saca cert Let's Encrypt solo).

## Parte 1 — DNS (Cloudflare)

En dash.cloudflare.com → coopeapp.com.ar → DNS → Records → Add record:

| Type | Name | IPv4 | Proxy status |
|------|------|------|--------------|
| A | @    | 178.105.15.189 | DNS only (nube GRIS) |
| A | www  | 178.105.15.189 | DNS only (nube GRIS) |

Nube **gris** a propósito: el origen maneja su propio TLS con Caddy. La nube
naranja rompe websockets/longpolling de Odoo y limita el tamaño de los POST.

Verificar propagación:
```bash
dig +short coopeapp.com.ar      # debe devolver 178.105.15.189
```

## Parte 2 — Abrir puertos 80/443

El curl a :8069 ya funcionaba (puerto abierto). Falta asegurar 80 y 443.

- Si hay **Hetzner Cloud Firewall**: agregar reglas inbound TCP 80 y 443.
- Si hay **ufw** en el VPS:
```bash
ssh coopeapp-vps "sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw status"
```

## Parte 3 — Instalar Caddy en el VPS

```bash
ssh coopeapp-vps
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

## Parte 4 — Caddyfile

`/etc/caddy/Caddyfile` (reemplazar todo el contenido):
```
coopeapp.com.ar {
    encode gzip zstd
    reverse_proxy localhost:8069
}

# www redirige a la raíz
www.coopeapp.com.ar {
    redir https://coopeapp.com.ar{uri} permanent
}
```
Aplicar:
```bash
ssh coopeapp-vps "sudo systemctl reload caddy && sudo systemctl status caddy --no-pager | head -5"
```
Caddy saca el certificado Let's Encrypt solo en el primer request (necesita
DNS apuntando + puerto 80 abierto). Si falla, ver: `sudo journalctl -u caddy -n 50`.

## Parte 5 — Odoo detrás de proxy

Para que Odoo confíe en el `X-Forwarded-Proto` de Caddy (URLs https correctas,
cookies seguras), agregar a `odoo.conf`:
```
proxy_mode = True
```
Está en `~/odoo-coop/` (montado en el contenedor). Editar y reiniciar:
```bash
ssh coopeapp-vps "cd ~/odoo-coop && grep -q '^proxy_mode' config/odoo.conf || echo 'proxy_mode = True' >> config/odoo.conf && docker compose restart odoo"
```
(ajustar la ruta del odoo.conf según dónde esté montado).

## Parte 6 — Verificar

```bash
curl -sS -o /dev/null -w "code=%{http_code} final=%{url_effective}\n" -L https://coopeapp.com.ar/app/ingresar
```
Esperado: `code=200 final=https://coopeapp.com.ar/app/ingresar`.

Luego en el celular: `https://coopeapp.com.ar/app/ingresar` → login tel + PIN.
Con HTTPS real ya funciona la **PWA instalable + offline** (el service worker
necesita contexto seguro).

## Cerrar el puerto 8069 (opcional, después de verificar)

Una vez que Caddy sirve todo por 443, conviene no exponer 8069 al público.
En el `docker-compose.yml`, cambiar el publish de `8069:8069` a
`127.0.0.1:8069:8069` y `docker compose up -d odoo`. Así solo Caddy (local)
llega a Odoo.
