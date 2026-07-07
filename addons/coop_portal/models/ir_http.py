from odoo import models
from odoo.http import request

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
