import json

from odoo import http
from odoo.http import request

MANIFEST = {
    'name': 'coopeapp',
    'short_name': 'coopeapp',
    'description': 'App de la cooperativa: avances, plata, obra, asamblea.',
    'start_url': '/app',
    'scope': '/app/',
    'display': 'standalone',
    'orientation': 'portrait',
    'background_color': '#ffffff',
    'theme_color': '#1a7f4e',
    'lang': 'es-AR',
    'icons': [{
        'src': '/coop_portal/static/img/icon.svg',
        'sizes': 'any',
        'type': 'image/svg+xml',
        'purpose': 'any maskable',
    }],
}

# Service worker: cachea el shell (network-first en GET, fallback a caché).
# Los POST no se cachean — la cola offline vive en la página (localStorage).
SERVICE_WORKER = """
const CACHE = 'coopeapp-v1';
const SHELL = ['/app', '/app/obra', '/app/plata', '/app/cargar', '/app/asamblea'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
  self.skipWaiting();
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(
    ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') { return; }
  e.respondWith(
    fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy).catch(() => {}));
      return res;
    }).catch(() => caches.match(req).then((m) => m || caches.match('/app')))
  );
});
"""

MEDIDAS = ('jornal', 'hora', 'tarea')


class CoopPwa(http.Controller):

    @http.route('/app/manifest.webmanifest', type='http', auth='public',
                website=False)
    def manifest(self, **kw):
        return request.make_response(json.dumps(MANIFEST), headers=[
            ('Content-Type', 'application/manifest+json'),
            ('Cache-Control', 'no-cache')])

    @http.route('/app/sw.js', type='http', auth='public', website=False)
    def service_worker(self, **kw):
        return request.make_response(SERVICE_WORKER, headers=[
            ('Content-Type', 'application/javascript'),
            ('Service-Worker-Allowed', '/app/'),
            ('Cache-Control', 'no-cache')])

    @http.route('/app/cargar/encolado', type='http', auth='user',
                website=False)
    def cargar_encolado(self, **kw):
        return request.render('coop_portal.cargar_encolado', {})

    @http.route('/app/cargar/sync', type='http', auth='user', website=False,
                methods=['POST'], csrf=True)
    def cargar_sync(self, item_id=None, cantidad=None, medida_trabajo=None,
                    cantidad_trabajo=None, **kw):
        """Sincroniza un avance cargado offline. csrf=True: la cola del cliente
        guarda el csrf_token de la página y lo reenvía. Solo crea el avance del
        socio logueado (record rule 'propio + borrador')."""
        member = request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid]),
             ('state', '=', 'active')], limit=1)
        item = request.env['coop.foja.item'].sudo().browse(
            int(item_id)).exists() if item_id else False

        def _num(v):
            try:
                return float(str(v).replace(',', '.'))
            except (TypeError, ValueError):
                return 0.0
        cant, trab = _num(cantidad), _num(cantidad_trabajo)
        ok = bool(member and item and cant > 0 and trab > 0
                  and medida_trabajo in MEDIDAS)
        if ok:
            request.env['coop.avance.medicion'].create({
                'foja_item_id': item.id, 'member_id': member.id,
                'cantidad': cant, 'medida_trabajo': medida_trabajo,
                'cantidad_trabajo': trab,
            })
        return request.make_response(
            json.dumps({'ok': ok}),
            headers=[('Content-Type', 'application/json')])
