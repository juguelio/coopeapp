from odoo import models, fields


class CoopNota(models.Model):
    _name = 'coop.nota'
    _description = 'Nota de obra'
    _order = 'create_date desc'

    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='cascade')
    texto = fields.Text(string='Nota', required=True)
    member_id = fields.Many2one(
        'coop.member', string='Autor', ondelete='set null')
