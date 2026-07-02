from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home

# Tokens de user-agent que identifican un celular/tablet. 'mobile' cubre
# Chrome/Safari/Firefox mobile; android/iphone/ipad por las dudas (iPad con
# "sitio de escritorio" se reporta Macintosh → va al backoffice, correcto
# para quien lo pide explícitamente).
_MOBILE_TOKENS = ('android', 'iphone', 'ipad', 'mobile', 'opera mini')


class CoopHome(Home):
    """Raíz por dispositivo (regla de alcance del plan canónico):
    parado en obra con el celu → /app; sentado a un escritorio → oficina
    (comportamiento estándar de Odoo: /odoo o /web/login)."""

    @http.route()
    def index(self, *args, **kw):
        ua = (request.httprequest.user_agent.string or '').lower()
        if any(t in ua for t in _MOBILE_TOKENS):
            return request.redirect('/app')
        return super().index(*args, **kw)
