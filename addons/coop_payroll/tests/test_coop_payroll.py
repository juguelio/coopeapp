from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestCoopPayroll(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Socio Test'})
        self.member = self.env['coop.member'].create({
            'name': 'Socio Test',
            'partner_id': self.partner.id,
            'dni': '99887766',
            'role': 'worker',
            'state': 'active',
            'date_admission': '2024-01-01',
        })
        self.payroll = self.env['coop.payroll'].create({
            'name': 'Liquidación Abril 2026',
            'member_id': self.member.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
            'hour_rate': 5000,
        })

    def test_payroll_creation(self):
        self.assertEqual(self.payroll.state, 'draft')
        self.assertEqual(self.payroll.net_amount, 0.0)

    def test_work_entries_compute_hours(self):
        self.env['coop.work.entry'].create({
            'payroll_id': self.payroll.id,
            'member_id': self.member.id,
            'date': '2026-04-01',
            'hours': 8.0,
            'work_type': 'normal',
        })
        self.env['coop.work.entry'].create({
            'payroll_id': self.payroll.id,
            'member_id': self.member.id,
            'date': '2026-04-02',
            'hours': 6.0,
            'work_type': 'normal',
        })
        self.assertEqual(self.payroll.total_hours, 14.0)
        self.assertEqual(self.payroll.hours_amount, 14.0 * 5000)

    def test_advance_discounted(self):
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo semana 1',
            'member_id': self.member.id,
            'amount': 20000,
            'date': '2026-04-05',
        })
        advance.action_approve()
        advance.write({'payroll_id': self.payroll.id})
        self.env['coop.work.entry'].create({
            'payroll_id': self.payroll.id,
            'member_id': self.member.id,
            'date': '2026-04-01',
            'hours': 10.0,
            'work_type': 'normal',
        })
        self.assertEqual(self.payroll.net_amount, (10.0 * 5000) - 20000)

    def test_full_lifecycle(self):
        self.payroll.action_send_to_review()
        self.assertEqual(self.payroll.state, 'review')
        self.payroll.action_member_agree()
        self.assertTrue(self.payroll.member_agrees)
        self.payroll.action_approve()
        self.assertEqual(self.payroll.state, 'approved')
        self.payroll.action_pay()
        self.assertEqual(self.payroll.state, 'paid')

    def test_invalid_dates(self):
        with self.assertRaises(ValidationError):
            self.env['coop.payroll'].create({
                'name': 'Test',
                'member_id': self.member.id,
                'date_from': '2026-04-30',
                'date_to': '2026-04-01',
                'hour_rate': 5000,
            })

    def test_negative_net_rejected_on_approve(self):
        """Aprobar una liquidación con neto negativo debe fallar."""
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo excesivo',
            'member_id': self.member.id,
            'amount': 50000,
            'date': '2026-04-01',
        })
        advance.action_approve()
        advance.write({'payroll_id': self.payroll.id})
        # Sin horas: gross=0, net = -50000
        self.payroll.action_send_to_review()
        with self.assertRaises(ValidationError):
            self.payroll.action_approve()

    def test_paid_payroll_immutable(self):
        """Una liquidación pagada no puede modificarse."""
        self.env['coop.work.entry'].create({
            'payroll_id': self.payroll.id,
            'member_id': self.member.id,
            'date': '2026-04-01',
            'hours': 10.0,
            'work_type': 'normal',
        })
        self.payroll.action_send_to_review()
        self.payroll.action_approve()
        self.payroll.action_pay()
        self.assertEqual(self.payroll.state, 'paid')
        with self.assertRaises(ValidationError):
            self.payroll.write({'bonus_amount': 1000})

    def test_member_cannot_approve_advance(self):
        """Un usuario con rol socio no puede aprobar anticipos."""
        group_member = self.env.ref('coop_members.group_coop_member')
        member_user = self.env['res.users'].create({
            'name': 'Usuario Socio Test',
            'login': 'socio_acl_test@coop.test',
            'groups_id': [(6, 0, [group_member.id])],
        })
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo para test ACL',
            'member_id': self.member.id,
            'amount': 5000,
            'date': '2026-04-01',
        })
        with self.assertRaises(AccessError):
            advance.with_user(member_user).action_approve()
