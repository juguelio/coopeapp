from odoo import models
from odoo.http import SessionExpiredException, request

# Rutas que un socio con "debe cambiar el PIN" SÍ puede usar sin haberlo
# cambiado: la propia pantalla de cambio, el login y el shell PWA.
_PIN_CHANGE_ALLOW = {
    '/app/cambiar-pin', '/app/cambiar-pin/guardar',
    '/app/ingresar', '/app/ingresar/entrar',
    '/app/manifest.webmanifest', '/app/sw.js',
}


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _dispatch(cls, endpoint):
        """Punto único de control: si el usuario logueado tiene el PIN inicial
        pendiente de cambio, cualquier acción dentro de /app lo manda a la
        pantalla de cambio de PIN (no solo las home). Aísla el enforcement en
        un solo lugar en vez de repetir la guarda en cada controlador."""
        if request.session.uid:
            path = request.httprequest.path
            if (path.startswith('/app')
                    and path not in _PIN_CHANGE_ALLOW):
                user = request.env.user
                if user and user.sudo().coop_pin_debe_cambiar:
                    return request.redirect('/app/cambiar-pin')
        return super()._dispatch(endpoint)

    @classmethod
    def _handle_error(cls, exception):
        """Sin sesión, /app manda al socio a /web/login (la pantalla de la
        oficina) en vez de a su propio login por teléfono+PIN. La PWA arranca
        en /app/ingresar y no lo sufre, pero el socio que escribe el dominio a
        mano en el celular sí cae ahí, el primer día.

        El redirect lo arma el dispatcher de Odoo junto con el logout de sesión
        y la rotación de cookie, que sí queremos conservar: por eso delegamos
        en super() y solo reescribimos el destino cuando el pedido venía de
        /app. Fuera de /app no se toca nada."""
        response = super()._handle_error(exception)
        if (isinstance(exception, SessionExpiredException)
                and request.httprequest.path.startswith('/app')
                and getattr(response, 'status_code', 0) in (301, 302, 303)):
            response.headers['Location'] = '/app/ingresar'
        return response
