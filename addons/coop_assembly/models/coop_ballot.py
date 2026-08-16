from odoo import api, fields, models
from odoo.exceptions import ValidationError


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

    @api.constrains('vote_id', 'member_id')
    def _check_socio_presente(self) -> None:
        """Solo vota el socio marcado presente en la asamblea.

        El quórum se calcula sobre la asistencia real, así que un voto de un
        ausente lo contradice: la votación quedaría decidida por gente que no
        cuenta para el quórum que la habilitó.
        """
        for ballot in self:
            asamblea = ballot.sudo().vote_id.assembly_id
            if ballot.member_id not in asamblea.sudo().attendee_ids:
                raise ValidationError(
                    'Para votar hay que estar marcado presente en la '
                    'asamblea. %s no figura entre los presentes.'
                    % ballot.member_id.name)

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
