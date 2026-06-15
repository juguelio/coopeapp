from odoo import http
from odoo.http import request


class CoopPortalAsamblea(http.Controller):
    """Asamblea en /app: el socio ve la asamblea en curso, sus puntos a
    votar, y vota en secreto. El voto crea un coop.ballot (único por socio
    y votación); los totales viven en coop.vote (agregado). Nadie ve el
    voto de otro (record rule)."""

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid]),
             ('state', '=', 'active')], limit=1)

    def _asamblea_actual(self):
        # convocada o en curso: durante ambas el socio puede marcar asistencia
        return request.env['coop.assembly'].sudo().search(
            [('state', 'in', ['draft', 'open'])], order='date desc', limit=1)

    def _mi_ballot(self, vote, member):
        return request.env['coop.ballot'].sudo().search(
            [('vote_id', '=', vote.id), ('member_id', '=', member.id)], limit=1)

    @http.route('/app/asamblea', type='http', auth='user', website=False)
    def asamblea(self, **kw):
        member = self._member()
        if not member:
            return request.redirect('/app')
        asamblea = self._asamblea_actual()
        if not asamblea:
            return request.render('coop_portal.asamblea_ninguna', {'member': member})
        votos = []
        for v in asamblea.sudo().vote_ids.sorted('sequence'):
            votos.append({'vote': v, 'mi_voto': self._mi_ballot(v, member)})
        return request.render('coop_portal.asamblea', {
            'member': member, 'asamblea': asamblea, 'votos': votos,
            'puntos': asamblea.sudo().point_ids.sorted('sequence'),
            'mi_presente': member in asamblea.attendee_ids,
            'point_state_labels': dict(request.env['coop.assembly.point']
                                       ._fields['state'].selection),
            'choice_labels': dict(request.env['coop.ballot']
                                  ._fields['choice'].selection),
        })

    @http.route('/app/asamblea/presente', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def asamblea_presente(self, **kw):
        member = self._member()
        asamblea = self._asamblea_actual()
        if member and asamblea and member not in asamblea.attendee_ids:
            asamblea.sudo().write({'attendee_ids': [(4, member.id)]})
        return request.redirect('/app/asamblea')

    @http.route('/app/votar', type='http', auth='user', website=False)
    def votar(self, vote_id, **kw):
        member = self._member()
        vote = request.env['coop.vote'].sudo().browse(int(vote_id)).exists()
        if not member or not vote or vote.state != 'open':
            return request.redirect('/app/asamblea')
        if self._mi_ballot(vote, member):
            return request.redirect('/app/asamblea')
        return request.render('coop_portal.votar', {
            'member': member, 'vote': vote,
        })

    @http.route('/app/votar/confirmar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def votar_confirmar(self, vote_id, choice, **kw):
        member = self._member()
        vote = request.env['coop.vote'].sudo().browse(int(vote_id)).exists()
        if not member or not vote or vote.state != 'open':
            return request.redirect('/app/asamblea')
        if choice not in ('yes', 'no', 'abstain'):
            return request.redirect('/app/asamblea')
        if not self._mi_ballot(vote, member):
            # crear como el usuario: la record rule (solo propio) aplica
            try:
                request.env['coop.ballot'].create({
                    'vote_id': vote.id, 'member_id': member.id, 'choice': choice,
                })
            except Exception:  # noqa: BLE001 — carrera: ya votó
                pass
        return request.render('coop_portal.votado', {
            'member': member, 'vote': vote,
        })
