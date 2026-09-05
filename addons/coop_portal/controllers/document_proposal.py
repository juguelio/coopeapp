from urllib.parse import urlencode

from odoo import http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request


class CoopPortalDocumentProposal(http.Controller):
    """Cola de revisión documental dentro de la app mobile-first.

    La lectura usa sudo filtrado por el rol de administrador cooperativo. Las
    acciones se ejecutan con request.env para que Odoo registre al usuario
    autenticado y aplique sus ACLs.
    """

    def _member(self):
        return request.env['coop.member'].sudo().search(
            [('partner_id.user_ids', 'in', [request.env.uid]),
             ('state', '=', 'active')], limit=1)

    def _admin(self):
        member = self._member()
        return member if member and member.role == 'manager' else False

    def _state_labels(self):
        return dict(request.env['coop.document.proposal']
                    ._fields['state'].selection)

    @http.route('/app/admin/revision-documental', type='http', auth='user',
                website=False)
    def revision_documental(self, **kw):
        member = self._admin()
        if not member:
            return request.redirect('/app')
        proposals = request.env['coop.document.proposal'].sudo().search(
            [('state', 'in', ['pending_review', 'hold', 'needs_correction'])],
            order='create_date desc, id desc')
        return request.render('coop_portal.admin_document_proposals', {
            'member': member,
            'proposals': proposals,
            'state_labels': self._state_labels(),
            'nav_rol': 'admin',
            'nav_activo': 'documentos',
        })

    @http.route('/app/admin/revision-documental/<int:proposal_id>',
                type='http', auth='user', website=False)
    def revision_detalle(self, proposal_id, **kw):
        member = self._admin()
        if not member:
            return request.redirect('/app')
        proposal = request.env['coop.document.proposal'].sudo().browse(
            proposal_id).exists()
        if not proposal:
            return request.redirect('/app/admin/revision-documental')
        return request.render('coop_portal.admin_document_proposal_detail', {
            'member': member,
            'proposal': proposal,
            'state_labels': self._state_labels(),
            'obras': request.env['project.project'].sudo().search([
                ('is_coop_obra', '=', True),
                ('estado_obra', 'in', ['planificacion', 'activa']),
            ], order='name'),
            'error': kw.get('error'),
            'nav_rol': 'admin',
            'nav_activo': 'documentos',
        })

    @http.route('/app/admin/revision-documental/accion', type='http',
                auth='user', website=False, methods=['POST'], csrf=True)
    def revision_accion(self, proposal_id=None, accion=None, **kw):
        member = self._admin()
        if not member:
            return request.redirect('/app')
        try:
            proposal = request.env['coop.document.proposal'].browse(
                int(proposal_id)).exists() if proposal_id else False
        except (TypeError, ValueError):
            proposal = False
        if not proposal:
            return request.redirect('/app/admin/revision-documental')
        try:
            obra = request.env['project.project'].sudo().browse(
                int(kw.get('obra_id'))).exists() if kw.get('obra_id') else False
        except (TypeError, ValueError):
            obra = False
        if obra and obra.is_coop_obra:
            proposal.write({'obra_id': obra.id})
        try:
            # Sin sudo: el usuario autenticado es quien decide y queda en la
            # auditoría de approved_by_id/reviewed_by_id.
            if accion == 'approve':
                proposal.action_approve()
            elif accion == 'correction':
                proposal.action_request_correction()
            elif accion == 'reject':
                proposal.action_reject()
            else:
                raise ValidationError('Acción de revisión desconocida.')
        except (UserError, ValidationError) as exc:
            return request.redirect(
                '/app/admin/revision-documental/%d?%s' % (
                    proposal.id, urlencode({'error': str(exc)})))
        return request.redirect(
            '/app/admin/revision-documental/%d?ok=1' % proposal.id)
