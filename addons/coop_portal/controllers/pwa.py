import json
import math
import re

from psycopg2 import IntegrityError

from odoo import http
from odoo.http import request

MANIFEST = {
    'name': 'coopeapp',
    'short_name': 'coopeapp',
    'description': 'App de la cooperativa: avances, plata, obra, asamblea.',
    # Arranca en el login del socio (teléfono+PIN). Si ya está logueado,
    # /app/ingresar redirige solo a /app. Así el socio nunca cae en /web/login.
    'start_url': '/app/ingresar',
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

# Nunca almacenar HTML autenticado: los teléfonos pueden compartirse entre
# socios. Al activar esta versión se borra el caché privado de la versión vieja.
SERVICE_WORKER = """
const CACHE = 'coopeapp-public-v2';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(
    ks.filter((k) => k.startsWith('coopeapp-') && k !== CACHE)
      .map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) { return; }
  const asset = url.pathname.startsWith('/coop_portal/static/');
  if (!asset && req.mode !== 'navigate') { return; }
  e.respondWith(fetch(req).then((res) => {
    if (asset && res.ok && !res.redirected) {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy).catch(() => {}));
    }
    return res;
  }).catch(async () => {
    if (asset) { return (await caches.match(req)) || Response.error(); }
    const queued = url.pathname === '/app/cargar/encolado';
    return new Response('<!doctype html><html lang="es"><meta charset="utf-8">'
      + '<meta name="viewport" content="width=device-width,initial-scale=1">'
      + '<title>coopeapp — Sin señal</title><body><main><h1>'
      + (queued ? 'Guardado en este teléfono' : 'Sin señal') + '</h1><p>'
      + (queued ? 'Tu carga se enviará al volver a abrir la app con conexión y con tu cuenta.'
                : 'Volvé a abrir esta página cuando recuperes la conexión.')
      + '</p><a href="/app">Volver a la app</a></main>'
      + '<script>window.addEventListener("online", function () {'
      + 'window.location.href = "/app";});</script></body></html>',
      {headers: {'Content-Type': 'text/html; charset=utf-8'}});
  }));
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

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid]),
             ('state', '=', 'active')], limit=1)

    def _item_del_socio(self, member, item_id):
        """Gemelo offline de `/app/cargar/confirmar`: el mismo control de
        pertenencia. La cola guarda el `item_id` en el teléfono, así que para
        el servidor es un id que llega de afuera, igual que uno adivinado."""
        obras = request.env['project.project'].sudo().search([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('socio_obra_ids', 'in', member.ids),
        ])
        try:
            pedido = int(item_id or 0)
        except (TypeError, ValueError):
            return request.env['coop.foja.item'].sudo().browse()
        return request.env['coop.foja.item'].sudo().search([
            ('id', '=', pedido), ('obra_id', 'in', obras.ids)])

    @http.route('/app/cargar/encolado', type='http', auth='user',
                website=False)
    def cargar_encolado(self, **kw):
        return request.render('coop_portal.cargar_encolado', {})

    @http.route('/app/cargar/sync', type='http', auth='user', website=False,
                methods=['POST'], csrf=True)
    def cargar_sync(self, item_id=None, cantidad=None, medida_trabajo=None,
                    cantidad_trabajo=None, queue_uid=None, sync_token=None, **kw):
        """Sincroniza un avance cargado offline. csrf=True: la cola del cliente
        renueva el csrf_token desde la página actual antes de enviarlo. Solo crea el avance del
        socio logueado (record rule 'propio + borrador')."""
        member = self._member()
        item = self._item_del_socio(member, item_id)

        def _num(v):
            try:
                numero = float(str(v).replace(',', '.'))
                return numero if math.isfinite(numero) else 0.0
            except (TypeError, ValueError):
                return 0.0
        cant, trab = _num(cantidad), _num(cantidad_trabajo)
        misma_cuenta = queue_uid is None or str(queue_uid) == str(request.env.uid)
        ok = bool(misma_cuenta and member and item and cant > 0 and trab > 0
                  and medida_trabajo in MEDIDAS)
        if sync_token and not re.fullmatch(r'[a-fA-F0-9-]{32,36}', sync_token):
            ok = False
        Avance = request.env['coop.avance.medicion']
        dominio_token = [('member_id', '=', member.id),
                         ('portal_sync_token', '=', sync_token)]
        # El ACK puede perderse con la señal después del INSERT. Un replay
        # reconoce el token propio, incluso si el coordinador ya validó la carga.
        existente = (Avance.sudo().search(dominio_token, limit=1)
                     if member and misma_cuenta and sync_token and ok else Avance)
        if ok and not existente:
            vals = {
                'foja_item_id': item.id, 'member_id': member.id,
                'cantidad': cant, 'medida_trabajo': medida_trabajo,
                'cantidad_trabajo': trab,
                'portal_sync_token': sync_token or False,
            }
            try:
                with request.env.cr.savepoint():
                    Avance.create(vals)
            except IntegrityError:
                # Dos pestañas pueden enviar el mismo token a la vez. La
                # restricción única decide; el savepoint mantiene sano el POST.
                if not sync_token or not Avance.sudo().search(dominio_token, limit=1):
                    raise
        return request.make_response(
            json.dumps({'ok': ok}),
            headers=[('Content-Type', 'application/json')])
