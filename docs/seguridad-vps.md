# Seguridad del VPS — análisis y plan

**Fecha:** 2026-08-27 · Disparado por el hallazgo de Code del 26/08:
*`odoo-admin` está en el grupo `docker`, y con eso se llega a root igual.*

---

## 1. El hallazgo es correcto, pero no es el agujero principal

Que `odoo-admin` esté en el grupo `docker` **sí** equivale a root: montás
`/etc/nginx` en un contenedor privilegiado y escribís lo que quieras. Está
documentado por el propio Docker. La consecuencia que anotó Code es exacta: la
contraseña de sudo no está protegiendo nada.

Pero `odoo-admin` **es** el administrador del servidor. Que el admin pueda
llegar a root no es una escalada: es su trabajo. Sacarlo del grupo `docker`
rompe el deploy, el backup y el mantenimiento, y lo obliga a `sudo docker`, que
es exactamente igual de root. **Costo alto, ganancia cero.**

Lo grave es la combinación con lo de abajo.

## 2. 🔴 El agujero: la llave de CI es una llave de root, sin restricción

`scripts/setup-ci-deploy.sh` instala la pubkey de CI en
`~/.ssh/authorized_keys` **tal cual, sin ninguna restricción**:

```bash
grep -qxF '$PUB' ~/.ssh/authorized_keys || echo '$PUB' >> ~/.ssh/authorized_keys
```

Sin `command=` ni `restrict`, esa llave abre **una shell interactiva completa**
como `odoo-admin`. Y por el punto 1, `odoo-admin` es root.

La privada de esa llave vive en los secrets de GitHub. Entonces, dicho en una
frase:

> **Cualquiera que comprometa la cuenta de GitHub —o que pueda correr un
> workflow en el repo— tiene root en el servidor de producción.**

No hace falta ni robar la llave: un workflow con
`ssh $VPS_USER@$VPS_HOST 'lo que sea'` corre con la llave que ya está cargada.

Eso es una superficie mucho más grande que el grupo `docker`, y es la que sí
conviene cerrar.

### 2b. De paso: la validación del input se aplica a medias

El workflow valida `github.event.inputs.modulos` contra
`*[!A-Za-z0-9_,-]*` — bien pensado, el comentario lo explica. Pero la rama
automática **no pasa por esa validación**: `MODS` sale de los nombres de
directorio bajo `addons/`, y un directorio puede llamarse con metacaracteres.
La misma validación tiene que correr para los dos caminos.

## 3. Lo que se propone

**No** sacar a `odoo-admin` del grupo `docker`. Sí acotar la llave de CI a lo
único que necesita hacer.

### 3.1 Forzar un comando para la llave de CI

En `~/.ssh/authorized_keys` del VPS, la línea de CI pasa a:

```
restrict,command="/home/odoo-admin/odoo-coop/ci-forced-command.sh" ssh-ed25519 AAAA... coopeapp-ci-deploy
```

`restrict` apaga port-forwarding, agent-forwarding, X11, PTY y `~/.ssh/rc`.
`command=` hace que **cualquier** cosa que pida el cliente sea reemplazada por
ese script; lo pedido queda en `$SSH_ORIGINAL_COMMAND`, como dato.

El script (`scripts/vps/ci-forced-command.sh`) acepta exactamente dos cosas:

1. el `rsync --server` que escribe **dentro de `~/odoo-coop/addons/`**
2. `deploy <lista-de-módulos>`, con la lista validada contra
   `^[A-Za-z0-9_,-]+$`

Cualquier otra cosa se rechaza y **se registra** en `~/odoo-coop/ci-deploy.log`.
Con eso, una llave de CI robada puede deployar módulos — que es su trabajo — y
no puede abrir una shell.

### 3.2 Rotar la llave de CI

Estuvo sin restricción desde que se creó, con alcance root y sin que estuviera
escrito en ningún lado. Rotarla es barato y cierra el período de exposición.

### 3.3 Higiene de la cuenta (verificar, no asumir)

- `PasswordAuthentication no` y `PermitRootLogin no` en `sshd_config`
- fail2ban activo
- revisar qué otras llaves hay en `authorized_keys` y si alguna no se reconoce

## 4. Lo que NO se hace, y por qué

| Idea | Por qué no |
|---|---|
| Sacar `odoo-admin` del grupo `docker` | Rompe deploy, backup y mantenimiento. `sudo docker` es igual de root. Ganancia real: cero. |
| Docker rootless | Cambio grande de infraestructura para un servidor de un solo inquilino. No paga. |
| Poner contraseña al sudo y confiar en eso | Es la ilusión que este documento existe para desarmar. |

## 5. Cómo se verifica que quedó bien

El paso que importa. Después de aplicar, **la llave de CI no tiene que poder
abrir una shell**:

```bash
ssh -i ~/.ssh/coopeapp_ci odoo-admin@178.105.15.189 'id'
# esperado: rechazo + línea en ci-deploy.log. Si imprime un uid, NO quedó puesto.
```

`scripts/verificar-llave-ci.sh` corre esa prueba y **falla si la llave todavía
puede ejecutar cosas**. Está escrito para poder dar rojo: si el chequeo no sabe
fallar, no es un chequeo.

> ⚠️ **Antes de tocar nada:** tu llave personal (`coopeapp-vps`) queda **sin
> restricción**. Es la red de seguridad. Aplicá el cambio, verificá con la
> personal que seguís entrando, y recién después probá que la de CI está
> acotada. Nunca al revés.
