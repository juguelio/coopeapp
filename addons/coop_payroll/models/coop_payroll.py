from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopPayroll(models.Model):
    _name = 'coop.payroll'
    _description = 'Liquidación a Socio'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc'

    # -------------------------------------------------------------------------
    # Identificación
    # -------------------------------------------------------------------------
    name = fields.Char(
        string='Referencia',
        required=True,
        default=lambda self: _('Nueva liquidación'),
        tracking=True,
    )
    member_id = fields.Many2one(
        'coop.member',
        string='Socio',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Cooperativa',
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    # -------------------------------------------------------------------------
    # Período
    # -------------------------------------------------------------------------
    date_from = fields.Date(
        string='Desde',
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        tracking=True,
    )

    # -------------------------------------------------------------------------
    # Estado — principio ACI: transparencia y control democrático
    # -------------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('review', 'En revisión por el socio'),
        ('approved', 'Aprobada'),
        ('paid', 'Pagada'),
        ('cancelled', 'Anulada'),
    ], string='Estado', default='draft', required=True, tracking=True)

    # -------------------------------------------------------------------------
    # Horas trabajadas
    # -------------------------------------------------------------------------
    work_entry_ids = fields.One2many(
        'coop.work.entry',
        'payroll_id',
        string='Registros de horas',
    )
    total_hours = fields.Float(
        string='Total horas trabajadas',
        compute='_compute_totals',
        store=True,
    )
    hour_rate = fields.Monetary(
        string='Valor hora',
        currency_field='currency_id',
        tracking=True,
    )
    hours_amount = fields.Monetary(
        string='Importe por horas',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )

    # -------------------------------------------------------------------------
    # Anticipos descontados
    # -------------------------------------------------------------------------
    advance_ids = fields.One2many(
        'coop.advance',
        'payroll_id',
        string='Anticipos descontados',
        domain=[('state', '=', 'approved')],
    )
    total_advances = fields.Monetary(
        string='Total anticipos',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )

    # -------------------------------------------------------------------------
    # Otros conceptos
    # -------------------------------------------------------------------------
    bonus_amount = fields.Monetary(
        string='Bonificaciones',
        currency_field='currency_id',
        default=0.0,
    )
    deduction_amount = fields.Monetary(
        string='Deducciones',
        currency_field='currency_id',
        default=0.0,
    )

    # -------------------------------------------------------------------------
    # Totales
    # -------------------------------------------------------------------------
    gross_amount = fields.Monetary(
        string='Importe bruto',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    net_amount = fields.Monetary(
        string='Importe neto a cobrar',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )

    # -------------------------------------------------------------------------
    # Observación del socio — principio ACI: control democrático
    # -------------------------------------------------------------------------
    member_observation = fields.Text(
        string='Observación del socio',
    )
    member_agrees = fields.Boolean(
        string='Socio conforme',
        default=False,
        tracking=True,
    )

    # -------------------------------------------------------------------------
    # Pago
    # -------------------------------------------------------------------------
    date_paid = fields.Date(
        string='Fecha de pago',
        tracking=True,
    )
    payment_method = fields.Selection([
        ('cash', 'Efectivo'),
        ('transfer', 'Transferencia bancaria'),
        ('check', 'Cheque'),
    ], string='Forma de pago', tracking=True)
    move_id = fields.Many2one(
        'account.move',
        string='Asiento contable',
        readonly=True,
    )
    notes = fields.Text(string='Notas internas')

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------
    @api.depends(
        'work_entry_ids.hours',
        'hour_rate',
        'advance_ids.amount',
        'bonus_amount',
        'deduction_amount',
    )
    def _compute_totals(self):
        for payroll in self:
            payroll.total_hours = sum(e.hours for e in payroll.work_entry_ids)
            payroll.hours_amount = payroll.total_hours * payroll.hour_rate
            payroll.total_advances = sum(a.amount for a in payroll.advance_ids)
            payroll.gross_amount = payroll.hours_amount + payroll.bonus_amount
            payroll.net_amount = (
                payroll.gross_amount
                - payroll.deduction_amount
                - payroll.total_advances
            )

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for payroll in self:
            if payroll.date_from and payroll.date_to:
                if payroll.date_to < payroll.date_from:
                    raise ValidationError(
                        _('La fecha de fin no puede ser anterior a la de inicio.')
                    )

    @api.constrains('net_amount')
    def _check_net_amount(self):
        for payroll in self:
            if payroll.state == 'approved' and payroll.net_amount < 0:
                raise ValidationError(
                    _('El importe neto no puede ser negativo. Revisá los anticipos.')
                )

    # -------------------------------------------------------------------------
    # Write lock — una liquidación pagada no se puede modificar
    # -------------------------------------------------------------------------
    def write(self, vals):
        if self.filtered(lambda p: p.state == 'paid'):
            raise ValidationError(_('Una liquidación pagada no puede modificarse.'))
        return super().write(vals)

    # -------------------------------------------------------------------------
    # Onchange
    # -------------------------------------------------------------------------
    @api.onchange('member_id')
    def _onchange_member_id(self):
        if self.member_id:
            self.name = f'Liquidación {self.member_id.name}'

    # -------------------------------------------------------------------------
    # Acciones de estado
    # -------------------------------------------------------------------------
    def action_send_to_review(self):
        """Envía la liquidación al socio para que la revise."""
        for payroll in self:
            payroll.write({'state': 'review'})
            payroll.message_post(
                body=_('Liquidación enviada al socio para revisión. El socio puede marcar observaciones.'),
                message_type='notification',
            )

    def action_approve(self):
        """Aprueba la liquidación, lista para pagar."""
        for payroll in self:
            if payroll.net_amount < 0:
                raise ValidationError(_('No se puede aprobar una liquidación con importe neto negativo.'))
            payroll.write({'state': 'approved'})
            payroll.message_post(
                body=_('Liquidación aprobada. Pendiente de pago.'),
                message_type='notification',
            )

    def action_pay(self):
        """Marca la liquidación como pagada."""
        for payroll in self:
            payroll.write({
                'state': 'paid',
                'date_paid': payroll.date_paid or fields.Date.today(),
            })
            payroll.message_post(
                body=_('Liquidación pagada el %s.') % payroll.date_paid,
                message_type='notification',
            )

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_member_agree(self):
        """El socio marca que está conforme con la liquidación."""
        self.write({'member_agrees': True})
        self.message_post(
            body=_('El socio confirmó estar conforme con esta liquidación.'),
            message_type='notification',
        )
