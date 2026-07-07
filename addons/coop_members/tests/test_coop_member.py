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

    def test_app_access_auto_provisioned(self):
        """Crear un socio con DNI y contacto crea el acceso a la app."""
        self.assertTrue(self.member.has_app_access)
        self.assertEqual(self.member.app_login, '30123456')
        # PIN inicial = últimos 4 del DNI
        self.assertTrue(self.member.app_user_id._verifica_pin('3456'))

    def test_coordinator_role_maps_to_group(self):
        """El rol Coordinador deja al usuario en el grupo coordinador."""
        partner = self.env['res.partner'].create({'name': 'Coord'})
        coord = self.env['coop.member'].create({
            'name': 'Coord', 'partner_id': partner.id,
            'dni': '28111222', 'role': 'coordinator',
        })
        grupo = self.env.ref('coop_members.group_coop_coordinador')
        self.assertIn(grupo, coord.app_user_id.groups_id)

    def test_role_change_syncs_group(self):
        """Cambiar el rol de un socio con acceso actualiza su grupo."""
        g_coord = self.env.ref('coop_members.group_coop_coordinador')
        g_mgr = self.env.ref('coop_members.group_coop_manager')
        self.assertNotIn(g_coord, self.member.app_user_id.groups_id)
        self.member.write({'role': 'coordinator'})
        self.assertIn(g_coord, self.member.app_user_id.groups_id)
        self.member.write({'role': 'manager'})
        self.assertIn(g_mgr, self.member.app_user_id.groups_id)
        # downgrade: manager → operario saca los grupos de más
        self.member.write({'role': 'worker'})
        self.assertNotIn(g_mgr, self.member.app_user_id.groups_id)
        self.assertNotIn(g_coord, self.member.app_user_id.groups_id)

    def test_reset_pin(self):
        """Reiniciar PIN lo vuelve a los últimos 4 del DNI."""
        self.member.app_user_id.set_coop_pin('9999')
        self.assertTrue(self.member.app_user_id._verifica_pin('9999'))
        self.member.action_resetear_pin()
        self.assertTrue(self.member.app_user_id._verifica_pin('3456'))

    def test_pin_wizard_sets_and_validates(self):
        """El asistente pone un PIN válido y rechaza uno inválido."""
        wiz = self.env['coop.member.pin.wizard'].create({
            'member_id': self.member.id, 'pin': '481516',
        })
        wiz.action_set_pin()
        self.assertTrue(self.member.app_user_id._verifica_pin('481516'))
        with self.assertRaises(ValidationError):
            self.env['coop.member.pin.wizard'].create({
                'member_id': self.member.id, 'pin': '12',  # muy corto
            })

    def test_first_login_must_change_pin(self):
        """El PIN inicial (auto) y el reseteado quedan marcados para cambiar;
        cuando el socio lo cambia (force_change=False) se libera."""
        user = self.member.app_user_id
        # alta automática → debe cambiar
        self.assertTrue(user.sudo().coop_pin_debe_cambiar)
        # el socio elige su PIN → ya no debe cambiar
        user.set_coop_pin('7788', force_change=False)
        self.assertFalse(user.sudo().coop_pin_debe_cambiar)
        # el admin lo resetea → vuelve a exigir cambio
        self.member.action_resetear_pin()
        self.assertTrue(user.sudo().coop_pin_debe_cambiar)

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
