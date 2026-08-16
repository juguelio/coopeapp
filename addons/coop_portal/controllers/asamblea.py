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

    def _nav_rol(self, member):
        """La asamblea es compartida: la barra inferior debe ser la del rol de
        quien la mira (síndico/admin/coordinador), no la del socio por defecto."""
        if member.role == 'syndic':
            return 'sindico'
        if member.role == 'manager':
            return 'admin'
        es_coord = request.env['project.project'].sudo().search_count([
            ('is_coop_obra', '=', True),
            ('estado_obra', 'in', ['planificacion', 'activa']),
            ('capataz_id', '=', member.id)])
        return 'coordinador' if es_coord else None

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
            return request.render('coop_portal.asamblea_ninguna', {
                'member': member, 'nav_rol': self._nav_rol(member),
                'nav_activo': 'asamblea'})
        votos = []
        for v in asamblea.sudo().vote_ids.sorted('sequence'):
            votos.append({'vote': v, 'mi_voto': self._mi_ballot(v, member)})
        return request.render('coop_portal.asamblea', {
            'member': member, 'asamblea': asamblea, 'votos': votos,
            'nav_rol': self._nav_rol(member), 'nav_activo': 'asamblea',
            'puntos': asamblea.sudo().point_ids.sorted('sequence'),
            'mi_presente': member in asamblea.attendee_ids,
            'mi_rol_firma': self._rol_firma(asamblea, member),
            'ya_firme': bool(asamblea.firma_ids.filtered(
                lambda f: f.member_id.id == member.id)),
            'point_state_labels': dict(request.env['coop.assembly.point']
                                       ._fields['state'].selection),
            'choice_labels': dict(request.env['coop.ballot']
                                  ._fields['choice'].selection),
        })

    def _rol_firma(self, asamblea, member):
        if member.id == asamblea.president_id.id:
            return 'presidente'
        if member.id == asamblea.secretary_id.id:
            return 'secretario'
        if member.role == 'syndic':
            return 'sindico'
        return False

    @http.route('/app/asamblea/firmar', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def asamblea_firmar(self, **kw):
        member = self._member()
        asamblea = self._asamblea_actual()
        if member and asamblea and asamblea.acta_texto:
            rol = self._rol_firma(asamblea, member)
            if rol:
                asamblea.sudo().action_firmar(member, rol)
        return request.redirect('/app/asamblea')

    @http.route('/app/asamblea/presente', type='http', auth='user',
                website=False, methods=['POST'], csrf=True)
    def asamblea_presente(self, **kw):
        member = self._member()
        asamblea = self._asamblea_actual()
        if member and asamblea and member not in asamblea.attendee_ids:
            asamblea.sudo().write({'attendee_ids': [(4, member.id)]})
        return request.redirect('/app/asamblea')

    def _puede_votar(self, vote, member):
        """El quórum sale de la asistencia real, así que solo vota quien está
        marcado presente. Sin esto la votación la puede decidir gente que no
        cuenta para el quórum que la habilitó."""
        return bool(member) and member in vote.sudo().assembly_id.attendee_ids

    @http.route('/app/votar', type='http', auth='user', website=False)
    def votar(self, vote_id, **kw):
        member = self._member()
        vote = request.env['coop.vote'].sudo().browse(int(vote_id)).exists()
        if not member or not vote or vote.state != 'open':
            return request.redirect('/app/asamblea')
        if not self._puede_votar(vote, member):
            return request.redirect('/app/asamblea')
        if self._mi_ballot(vote, member):
            return request.redirect('/app/asamblea')
        return request.render('coop_portal.votar', {
            'member': member, 'vote': vote,
            'nav_rol': self._nav_rol(member), 'nav_activo': 'asamblea',
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
        if not self._puede_votar(vote, member):
            return request.redirect('/app/asamblea')
        if not self._mi_ballot(vote, member):
            # crear como el usuario: la record rule (solo propio) aplica
            try:
                request.env['coop.ballot'].create({
                    'vote_id': vote.id, 'member_id': member.id, 'choice': choice,
                })
            except Exception:  # noqa: BLE001 — carrera: ya votó
                pass
            # Si el voto no quedó, no mostrar la pantalla de "listo": el socio
            # se iría creyendo que votó. Vuelve a la asamblea, que muestra el
            # estado real de cada punto.
            if not self._mi_ballot(vote, member):
                return request.redirect('/app/asamblea')
        return request.render('coop_portal.votado', {
            'member': member, 'vote': vote,
            'nav_rol': self._nav_rol(member), 'nav_activo': 'asamblea',
        })
