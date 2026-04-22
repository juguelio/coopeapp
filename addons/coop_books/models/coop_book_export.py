from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CoopBookExport(models.TransientModel):
    _name = 'coop.book.export'
    _description = 'Generador de Libros Cooperativos INAES/IPCyMER'

    BOOK_REPORT_MAP = {
        'registro_asociados': 'coop_books.report_action_registro_asociados',
        'actas_asamblea':     'coop_books.report_action_actas_asamblea',
        'actas_consejo':      'coop_books.report_action_actas_consejo',
        'liquidaciones':      'coop_books.report_action_liquidaciones',
        'inventario_balance': 'coop_books.report_action_inventario_balance',
    }

    book_type = fields.Selection([
        ('registro_asociados', 'Registro de Asociados'),
        ('actas_asamblea',     'Actas de Asamblea'),
        ('actas_consejo',      'Actas del Consejo de Administración'),
        ('liquidaciones',      'Liquidaciones a Socios'),
        ('inventario_balance', 'Inventario y Capital Social'),
    ], string='Libro', required=True)

    date_from = fields.Date(string='Desde', required=True)
    date_to   = fields.Date(string='Hasta', required=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise ValidationError(_('La fecha de fin no puede ser anterior a la de inicio.'))

    # -------------------------------------------------------------------------
    # Acción principal
    # -------------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        report_xmlid = self.BOOK_REPORT_MAP[self.book_type]
        return self.env.ref(report_xmlid).report_action(self)

    # -------------------------------------------------------------------------
    # Métodos de datos — llamados desde las plantillas QWeb
    # -------------------------------------------------------------------------
    def get_members(self):
        """Socios admitidos hasta date_to, activos o dados de baja en el período."""
        self.ensure_one()
        domain = [
            ('date_admission', '<=', self.date_to),
            '|',
            ('date_leaving', '=', False),
            ('date_leaving', '>=', self.date_from),
        ]
        return self.env['coop.member'].search(domain, order='date_admission asc')

    def get_assemblies(self, assembly_type):
        """Asambleas del tipo dado dentro del rango de fechas."""
        self.ensure_one()
        return self.env['coop.assembly'].search([
            ('assembly_type', '=', assembly_type),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'closed'),
        ], order='date asc')

    def get_payrolls(self):
        """Liquidaciones aprobadas o pagadas con período dentro del rango."""
        self.ensure_one()
        return self.env['coop.payroll'].search([
            ('date_from', '>=', self.date_from),
            ('date_to', '<=', self.date_to),
            ('state', 'in', ('approved', 'paid')),
        ], order='member_id asc, date_from asc')

    def get_capital_summary(self):
        """Capital social por socio: aportes confirmados hasta date_to."""
        self.ensure_one()
        members = self.env['coop.member'].search(
            [('date_admission', '<=', self.date_to)],
            order='name asc',
        )
        rows = []
        for member in members:
            confirmed = member.contribution_ids.filtered(
                lambda c: c.state == 'confirmed' and c.date <= self.date_to
            )
            total_in  = sum(c.amount for c in confirmed if c.type == 'contribution')
            total_out = sum(c.amount for c in confirmed if c.type == 'withdrawal')
            rows.append({
                'member':   member,
                'aportado': total_in,
                'retirado': total_out,
                'capital':  total_in - total_out,
            })
        return rows
