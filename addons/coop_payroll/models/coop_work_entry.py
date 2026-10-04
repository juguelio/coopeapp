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

    def _check_paid_payroll(self, payrolls):
        if payrolls.filtered(lambda p: p.state == 'paid'):
            raise ValidationError(_('No se pueden modificar horas de una liquidación pagada.'))

    @api.model_create_multi
    def create(self, vals_list):
        default_payroll = self.default_get(['payroll_id']).get('payroll_id')
        self._check_paid_payroll(self.env['coop.payroll'].browse([
            vals.get('payroll_id', default_payroll) for vals in vals_list
            if vals.get('payroll_id', default_payroll)
        ]))
        return super().create(vals_list)

    def write(self, vals):
        payrolls = self.mapped('payroll_id')
        if vals.get('payroll_id'):
            payrolls |= self.env['coop.payroll'].browse(vals['payroll_id'])
        self._check_paid_payroll(payrolls)
        return super().write(vals)

    def unlink(self):
        self._check_paid_payroll(self.mapped('payroll_id'))
        return super().unlink()

    @api.constrains('member_id', 'payroll_id')
    def _check_payroll_member(self):
        for entry in self:
            if entry.payroll_id and entry.member_id != entry.payroll_id.member_id:
                raise ValidationError(_('Las horas y la liquidación deben pertenecer al mismo socio.'))
