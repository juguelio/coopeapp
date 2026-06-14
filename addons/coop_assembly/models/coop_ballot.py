from odoo import api, fields, models


class CoopBallot(models.Model):
    """Voto individual y secreto de un socio en una votación.
    Alimenta los contadores agregados de coop.vote. Nadie ve el voto de
    otro: la record rule restringe la lectura al propio socio (los totales
    se ven en coop.vote, que es agregado)."""
    _name = 'coop.ballot'
    _description = 'Voto individual de socio'
    _order = 'create_date desc'

    vote_id = fields.Many2one(
        'coop.vote', string='Votación', required=True, ondelete='cascade')
    assembly_id = fields.Many2one(
        related='vote_id.assembly_id', string='Asamblea', store=True)
    member_id = fields.Many2one(
        'coop.member', string='Socio', required=True, ondelete='restrict')
    choice = fields.Selection([
        ('yes', 'A favor'),
        ('no', 'En contra'),
        ('abstain', 'Abstención'),
    ], string='Voto', required=True)

    _sql_constraints = [
        ('un_voto_por_socio', 'UNIQUE(vote_id, member_id)',
         'Cada socio vota una sola vez por votación.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        ballots = super().create(vals_list)
        ballots.vote_id._sync_counters()
        return ballots

    def write(self, vals):
        res = super().write(vals)
        self.vote_id._sync_counters()
        return res

    def unlink(self):
        votes = self.vote_id
        res = super().unlink()
        votes._sync_counters()
        return res
