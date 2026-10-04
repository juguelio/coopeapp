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

    def _member_user(self):
        return self.env['res.users'].create({
            'name': 'Socio Liquidación', 'login': 'socio_liquidacion_test',
            'partner_id': self.partner.id,
            'groups_id': [(6, 0, [self.env.ref('coop_members.group_coop_member').id])],
        })

    def test_member_only_changes_review_feedback(self):
        payroll = self.payroll.with_user(self._member_user())
        self.payroll.action_send_to_review()
        payroll.write({'member_observation': 'Revisado', 'member_agrees': True})
        for values in ({'hour_rate': 999999}, {'state': 'paid'}, {'bonus_amount': 1000}):
            with self.assertRaises(AccessError):
                payroll.write(values)

    def test_member_cannot_create_approved_advance(self):
        with self.assertRaises(AccessError):
            self.env['coop.advance'].with_user(self._member_user()).create({
                'name': 'Autorización propia', 'member_id': self.member.id,
                'amount': 100, 'state': 'approved',
            })

    def test_advance_state_recomputes_net(self):
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo', 'member_id': self.member.id,
            'amount': 100, 'payroll_id': self.payroll.id,
        })
        self.assertEqual(self.payroll.total_advances, 0)
        advance.action_approve()
        self.assertEqual(self.payroll.total_advances, 100)
        advance.action_reject()
        self.assertEqual(self.payroll.total_advances, 0)

    def test_paid_payroll_blocks_child_mutations(self):
        entry = self.env['coop.work.entry'].create({
            'member_id': self.member.id, 'payroll_id': self.payroll.id, 'hours': 8,
        })
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo', 'member_id': self.member.id,
            'amount': 100, 'state': 'approved', 'payroll_id': self.payroll.id,
        })
        self.payroll.action_send_to_review()
        self.payroll.action_approve()
        self.payroll.action_pay()
        for record, values in ((entry, {'hours': 10}), (entry, {'payroll_id': False}),
                               (advance, {'amount': 200}), (advance, {'state': 'rejected'})):
            with self.assertRaises(ValidationError):
                record.write(values)
        with self.assertRaises(ValidationError):
            self.env['coop.work.entry'].create({
                'member_id': self.member.id, 'payroll_id': self.payroll.id, 'hours': 1,
            })

    def test_cannot_pay_before_approval(self):
        with self.assertRaises(ValidationError):
            self.payroll.action_pay()

    def test_manager_can_read_and_approve_other_members_advance(self):
        manager = self.env['res.users'].create({
            'name': 'Manager Liquidación', 'login': 'manager_liquidacion_test',
            'email': 'manager_liquidacion@coop.test',
            'groups_id': [(6, 0, [self.env.ref('coop_members.group_coop_manager').id])],
        })
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo socio', 'member_id': self.member.id, 'amount': 100,
        })
        self.assertIn(advance, self.env['coop.advance'].with_user(manager).search([]))
        advance.with_user(manager).action_approve()
        self.assertEqual(advance.state, 'approved')

    def test_paid_payroll_blocks_context_default_children(self):
        self.payroll.action_send_to_review()
        self.payroll.action_approve()
        self.payroll.action_pay()
        for model, values in (
            ('coop.work.entry', {'hours': 1}),
            ('coop.advance', {'name': 'Anticipo', 'amount': 100}),
        ):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.env[model].with_context(default_payroll_id=self.payroll.id).create(
                    dict(values, member_id=self.member.id))

    def test_cannot_reassign_payroll_with_another_members_hours(self):
        self.env['coop.work.entry'].create({
            'member_id': self.member.id, 'payroll_id': self.payroll.id, 'hours': 8,
        })
        other = self.env['coop.member'].create({
            'name': 'Otro socio', 'dni': '99887765',
            'partner_id': self.env['res.partner'].create({'name': 'Otro'}).id,
        })
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.payroll.member_id = other

    def test_cannot_create_paid_payroll_with_negative_net(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['coop.payroll'].create({
                'member_id': self.member.id, 'date_from': '2026-04-01',
                'date_to': '2026-04-30', 'state': 'paid', 'deduction_amount': 100,
            })

    def test_syndic_reads_all_payrolls_without_approving(self):
        syndic = self.env['res.users'].create({
            'name': 'Síndico liquidaciones', 'login': 'sindico_payroll_test',
            'groups_id': [(6, 0, [self.env.ref('coop_members.group_coop_syndic').id])],
        })
        advance = self.env['coop.advance'].create({
            'name': 'Anticipo fiscalizado', 'member_id': self.member.id, 'amount': 100,
        })
        self.assertIn(self.payroll, self.env['coop.payroll'].with_user(syndic).search([]))
        self.assertIn(advance, self.env['coop.advance'].with_user(syndic).search([]))
        self.payroll.action_send_to_review()
        with self.assertRaises(AccessError):
            self.payroll.with_user(syndic).action_approve()
        with self.assertRaises(AccessError):
            advance.with_user(syndic).action_approve()

    def test_phone_only_manager_can_complete_financial_actions(self):
        manager = self.env['res.users'].create({
            'name': 'Admin sin correo', 'login': 'manager_phone_only_test',
            'email': False,
            'groups_id': [(6, 0, [self.env.ref('coop_members.group_coop_manager').id])],
        })
        self.member.with_user(manager).action_approve()
        self.member.with_user(manager).write({'role': 'coordinator'})
        contribution = self.env['coop.contribution'].with_user(manager).create({
            'member_id': self.member.id, 'name': 'Aporte sin correo', 'amount': 100,
        })
        contribution.action_confirm()
        advance = self.env['coop.advance'].with_user(manager).create({
            'name': 'Anticipo sin correo', 'member_id': self.member.id, 'amount': 100,
        })
        advance.action_approve()
        advance.action_reject()
        payroll = self.payroll.with_user(manager)
        payroll.action_send_to_review()
        payroll.action_approve()
        payroll.action_pay()
        self.assertEqual(payroll.state, 'paid')
        audit = payroll.message_ids.filtered(lambda m: 'Liquidación pagada' in (m.body or ''))
        self.assertEqual(audit.author_id, manager.partner_id)
