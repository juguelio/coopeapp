from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestCoopMember(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Juan Pérez',
            'email': 'juan@coopejemplo.org',
        })
        self.member = self.env['coop.member'].create({
            'name': 'Juan Pérez',
            'partner_id': self.partner.id,
            'dni': '30123456',
            'cuil': '20-30123456-7',
            'role': 'worker',
            'state': 'prospect',
        })

    def test_member_creation(self):
        """Un socio se crea como postulante por defecto."""
        self.assertEqual(self.member.state, 'prospect')
        self.assertEqual(self.member.social_capital, 0.0)

    def test_approve_member(self):
        """Aprobar un postulante lo pasa a activo."""
        self.member.action_approve()
        self.assertEqual(self.member.state, 'active')
        self.assertTrue(self.member.date_admission)

    def test_contribution_increases_capital(self):
        """Un aporte confirmado aumenta el capital social."""
        self.member.action_approve()
        contribution = self.env['coop.contribution'].create({
            'member_id': self.member.id,
            'name': 'Aporte inicial',
            'type': 'contribution',
            'amount': 50000,
            'date': '2024-01-01',
        })
        contribution.action_confirm()
        self.assertEqual(self.member.social_capital, 50000)

    def test_withdrawal_decreases_capital(self):
        """Un retiro confirmado reduce el capital social."""
        self.member.action_approve()
        self.env['coop.contribution'].create({
            'member_id': self.member.id,
            'name': 'Aporte',
            'type': 'contribution',
            'amount': 100000,
            'date': '2024-01-01',
            'state': 'confirmed',
        })
        withdrawal = self.env['coop.contribution'].create({
            'member_id': self.member.id,
            'name': 'Retiro parcial',
            'type': 'withdrawal',
            'amount': 30000,
            'date': '2024-02-01',
        })
        withdrawal.action_confirm()
        self.assertEqual(self.member.social_capital, 70000)

    def test_dni_unique_constraint(self):
        """No pueden existir dos socios con el mismo DNI."""
        partner2 = self.env['res.partner'].create({'name': 'Otra Persona'})
        with self.assertRaises(Exception):
            self.env['coop.member'].create({
                'name': 'Otra Persona',
                'partner_id': partner2.id,
                'dni': '30123456',  # mismo DNI
                'role': 'worker',
            })

    def test_leaving_date_after_admission(self):
        """La fecha de baja no puede ser anterior a la de ingreso."""
        self.member.action_approve()
        with self.assertRaises(ValidationError):
            self.member.write({
                'date_leaving': '2000-01-01',  # anterior al ingreso
            })

    def test_full_lifecycle(self):
        """Un socio puede pasar por todo el ciclo de vida."""
        # postulante → activo
        self.member.action_approve()
        self.assertEqual(self.member.state, 'active')
        # activo → suspendido
        self.member.action_suspend()
        self.assertEqual(self.member.state, 'suspended')
        # suspendido → reactivado
        self.member.action_reactivate()
        self.assertEqual(self.member.state, 'active')
        # activo → baja en proceso → ex socio
        self.member.action_start_leaving()
        self.assertEqual(self.member.state, 'leaving')
        self.member.action_confirm_leaving()
        self.assertEqual(self.member.state, 'former')
