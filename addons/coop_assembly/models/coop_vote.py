from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopVote(models.Model):
    _name = 'coop.vote'
    _description = 'Votación en Asamblea'
    _inherit = ['mail.thread']
    _order = 'sequence'

    name = fields.Char(string='Moción', required=True, tracking=True)
    sequence = fields.Integer(default=10)
    assembly_id = fields.Many2one('coop.assembly', string='Asamblea', required=True, ondelete='cascade')

    vote_type = fields.Selection([
        ('simple', 'Mayoría simple'),
        ('absolute', 'Mayoría absoluta (50%+1)'),
        ('two_thirds', 'Dos tercios'),
        ('unanimous', 'Unanimidad'),
    ], string='Tipo de mayoría', default='simple', required=True)

    is_secret = fields.Boolean(string='Voto secreto', default=False)

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('open', 'Votación abierta'),
        ('closed', 'Cerrada'),
    ], string='Estado', default='pending', required=True, tracking=True)

    votes_yes = fields.Integer(string='Votos a favor', default=0)
    votes_no = fields.Integer(string='Votos en contra', default=0)
    votes_abstain = fields.Integer(string='Abstenciones', default=0)

    ballot_ids = fields.One2many('coop.ballot', 'vote_id', string='Votos individuales')
    ballot_count = fields.Integer(string='Votaron', compute='_compute_ballot_count')

    total_votes = fields.Integer(string='Total votos', compute='_compute_results', store=True)
    approved = fields.Boolean(string='Aprobada', compute='_compute_results', store=True)
    result_summary = fields.Char(string='Resultado', compute='_compute_results', store=True)

    description = fields.Text(string='Descripción de la moción')
    notes = fields.Text(string='Observaciones')

    @api.depends('votes_yes', 'votes_no', 'votes_abstain', 'vote_type')
    def _compute_results(self):
        for vote in self:
            total = vote.votes_yes + vote.votes_no + vote.votes_abstain
            vote.total_votes = total

            if total == 0:
                vote.approved = False
                vote.result_summary = 'Sin votos'
                continue

            percentage_yes = vote.votes_yes / total * 100

            if vote.vote_type == 'simple':
                vote.approved = vote.votes_yes > vote.votes_no
            elif vote.vote_type == 'absolute':
                vote.approved = percentage_yes > 50
            elif vote.vote_type == 'two_thirds':
                vote.approved = percentage_yes >= 66.67
            elif vote.vote_type == 'unanimous':
                vote.approved = vote.votes_no == 0 and vote.votes_abstain == 0

            result = 'APROBADA' if vote.approved else 'RECHAZADA'
            vote.result_summary = (
                f'{result} — {vote.votes_yes} a favor, '
                f'{vote.votes_no} en contra, '
                f'{vote.votes_abstain} abstenciones'
            )

    def _compute_ballot_count(self):
        for vote in self:
            vote.ballot_count = len(vote.ballot_ids)

    def _sync_counters(self):
        """Recalcula los contadores agregados desde los votos individuales.
        Con sudo: necesita ver todos los ballots (que son secretos por rule)."""
        for vote in self:
            ballots = vote.sudo().ballot_ids
            vote.sudo().write({
                'votes_yes': len(ballots.filtered(lambda b: b.choice == 'yes')),
                'votes_no': len(ballots.filtered(lambda b: b.choice == 'no')),
                'votes_abstain': len(ballots.filtered(lambda b: b.choice == 'abstain')),
            })

    def action_open_vote(self):
        self.write({'state': 'open'})
        self.message_post(body=_('Votación abierta.'))

    def action_close_vote(self):
        self.write({'state': 'closed'})
        self.message_post(
            body=_('Votación cerrada. Resultado: %s') % self.result_summary
        )
