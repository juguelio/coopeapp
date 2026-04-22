from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopWorkEntry(models.Model):
    _name = 'coop.work.entry'
    _description = 'Registro de Horas Trabajadas'
    _order = 'date desc'

    payroll_id = fields.Many2one('coop.payroll', string='Liquidación', ondelete='cascade')
    member_id = fields.Many2one('coop.member', string='Socio', required=True, ondelete='restrict')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    hours = fields.Float(string='Horas', required=True)
    description = fields.Char(string='Descripción / Tarea')
    work_type = fields.Selection([
        ('normal', 'Jornada normal'),
        ('overtime', 'Horas extra'),
        ('holiday', 'Feriado'),
        ('training', 'Formación / Capacitación'),
    ], string='Tipo', default='normal', required=True)
    verified = fields.Boolean(string='Verificado por capataz', default=False)

    _sql_constraints = [
        ('hours_positive', 'CHECK(hours > 0)', 'Las horas deben ser mayor a cero.'),
        ('hours_max', 'CHECK(hours <= 24)', 'No se pueden registrar más de 24 horas por día.'),
    ]

    @api.constrains('hours')
    def _check_hours(self):
        for entry in self:
            if entry.hours <= 0:
                raise ValidationError(_('Las horas trabajadas deben ser mayor a cero.'))
