from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from datetime import date


@tagged('post_install', '-at_install')
class TestCoopBooks(TransactionCase):

    def setUp(self):
        super().setUp()
        # Socios
        self.partner1 = self.env['res.partner'].create({'name': 'Ana Soria'})
        self.partner2 = self.env['res.partner'].create({'name': 'Luis Perón'})
        self.member1 = self.env['coop.member'].create({
            'name': 'Ana Soria',
            'partner_id': self.partner1.id,
            'dni': '30111222',
            'state': 'active',
            'date_admission': '2024-01-15',
        })
        self.member2 = self.env['coop.member'].create({
            'name': 'Luis Perón',
            'partner_id': self.partner2.id,
            'dni': '25444555',
            'state': 'active',
            'date_admission': '2024-03-01',
        })
        # Aportes confirmados
        contrib = self.env['coop.contribution']
        for member, amount in [(self.member1, 50000), (self.member2, 30000)]:
            c = contrib.create({
                'member_id': member.id,
                'name': f'Aporte inicial {member.name}',
                'type': 'contribution',
                'amount': amount,
                'date': '2024-01-15',
            })
            c.action_confirm()

        # Wizard base reutilizable en tests
        self.wizard = self.env['coop.book.export'].create({
            'book_type': 'registro_asociados',
            'date_from': '2024-01-01',
            'date_to': '2026-12-31',
        })

    # -------------------------------------------------------------------------
    # Validaciones del wizard
    # -------------------------------------------------------------------------
    def test_date_validation(self):
        with self.assertRaises(ValidationError):
            self.env['coop.book.export'].create({
                'book_type': 'registro_asociados',
                'date_from': '2026-12-31',
                'date_to': '2026-01-01',
            })

    # -------------------------------------------------------------------------
    # get_members
    # -------------------------------------------------------------------------
    def test_get_members_returns_active(self):
        members = self.wizard.get_members()
        self.assertIn(self.member1, members)
        self.assertIn(self.member2, members)

    def test_get_members_excludes_out_of_range(self):
        """Socio admitido después de date_to no aparece."""
        partner3 = self.env['res.partner'].create({'name': 'Nuevo Socio'})
        self.env['coop.member'].create({
            'name': 'Nuevo Socio',
            'partner_id': partner3.id,
            'dni': '11223344',
            'state': 'active',
            'date_admission': '2027-01-01',
        })
        wizard = self.env['coop.book.export'].create({
            'book_type': 'registro_asociados',
            'date_from': '2024-01-01',
            'date_to': '2026-12-31',
        })
        names = wizard.get_members().mapped('name')
        self.assertNotIn('Nuevo Socio', names)

    # -------------------------------------------------------------------------
    # get_assemblies
    # -------------------------------------------------------------------------
    def test_get_assemblies_ordinary(self):
        asamblea = self.env['coop.assembly'].create({
            'name': 'Asamblea Ordinaria 2025',
            'assembly_type': 'ordinary',
            'date': '2025-03-15',
            'state': 'closed',
        })
        assemblies = self.wizard.get_assemblies('ordinary')
        self.assertIn(asamblea, assemblies)

    def test_get_assemblies_excludes_board(self):
        """Las reuniones de Consejo no aparecen en actas de asamblea."""
        self.env['coop.assembly'].create({
            'name': 'Reunión Consejo',
            'assembly_type': 'board',
            'date': '2025-04-10',
            'state': 'closed',
        })
        assemblies = self.wizard.get_assemblies('ordinary')
        types = assemblies.mapped('assembly_type')
        self.assertNotIn('board', types)

    def test_get_assemblies_excludes_open(self):
        """Asambleas no cerradas no aparecen en el libro."""
        self.env['coop.assembly'].create({
            'name': 'Asamblea abierta',
            'assembly_type': 'ordinary',
            'date': '2025-05-01',
            'state': 'open',
        })
        assemblies = self.wizard.get_assemblies('ordinary')
        for a in assemblies:
            self.assertEqual(a.state, 'closed')

    # -------------------------------------------------------------------------
    # get_payrolls
    # -------------------------------------------------------------------------
    def test_get_payrolls_returns_approved_and_paid(self):
        payroll = self.env['coop.payroll'].create({
            'name': 'Liquidación test',
            'member_id': self.member1.id,
            'date_from': '2026-01-01',
            'date_to': '2026-01-31',
            'hour_rate': 3000,
        })
        payroll.action_send_to_review()
        payroll.action_approve()
        payrolls = self.wizard.get_payrolls()
        self.assertIn(payroll, payrolls)

    def test_get_payrolls_excludes_draft(self):
        self.env['coop.payroll'].create({
            'name': 'Liquidación borrador',
            'member_id': self.member1.id,
            'date_from': '2026-02-01',
            'date_to': '2026-02-28',
            'hour_rate': 3000,
        })
        payrolls = self.wizard.get_payrolls()
        for p in payrolls:
            self.assertIn(p.state, ('approved', 'paid'))

    # -------------------------------------------------------------------------
    # get_capital_summary
    # -------------------------------------------------------------------------
    def test_get_capital_summary_totals(self):
        rows = self.wizard.get_capital_summary()
        members_in_rows = [r['member'] for r in rows]
        self.assertIn(self.member1, members_in_rows)
        row1 = next(r for r in rows if r['member'] == self.member1)
        self.assertEqual(row1['aportado'], 50000)
        self.assertEqual(row1['capital'], 50000)

    def test_get_capital_summary_deducts_withdrawals(self):
        retiro = self.env['coop.contribution'].create({
            'member_id': self.member1.id,
            'name': 'Retiro parcial',
            'type': 'withdrawal',
            'amount': 10000,
            'date': '2025-06-01',
        })
        retiro.action_confirm()
        rows = self.wizard.get_capital_summary()
        row1 = next(r for r in rows if r['member'] == self.member1)
        self.assertEqual(row1['capital'], 40000)
