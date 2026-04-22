from odoo import models, fields


class CoopWorkEntry(models.Model):
    _inherit = 'coop.work.entry'

    obra_id = fields.Many2one(
        'project.project', string='Obra',
        domain=[('is_coop_obra', '=', True)], ondelete='restrict')
