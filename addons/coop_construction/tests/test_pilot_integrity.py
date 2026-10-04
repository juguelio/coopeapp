from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPilotIntegrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Pilot worker', 'login': 'pilot.integrity.worker',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id,
                cls.env.ref('coop_members.group_coop_member').id])],
        })
        cls.member = cls.env['coop.member'].with_context(skip_portal_user=True).create({
            'name': 'Pilot worker', 'dni': '77888991',
            'partner_id': cls.user.partner_id.id, 'state': 'active',
            'date_admission': '2026-01-01',
        })
        cls.obra = cls.env['project.project'].create({
            'name': 'Pilot integrity', 'is_coop_obra': True,
            'socio_obra_ids': [(6, 0, cls.member.ids)],
        })
        cls.item = cls.env['coop.foja.item'].create({
            'obra_id': cls.obra.id, 'item': '1', 'name': 'Pared',
            'uom': 'm2', 'cantidad': 100, 'precio_unitario': 10,
        })
        cls.avance = cls.env['coop.avance.medicion'].create({
            'foja_item_id': cls.item.id, 'member_id': cls.member.id,
            'cantidad': 10,
        })
        cls.otro = cls.env['coop.trabajo.otro'].create({
            'obra_id': cls.obra.id, 'member_id': cls.member.id,
            'descripcion': 'Trabajo libre',
        })
        cls.material = cls.env['coop.material'].create({'name': 'Cemento piloto', 'uom': 'bolsa'})
        cls.pedido = cls.env['coop.pedido.material'].create({
            'obra_id': cls.obra.id, 'member_id': cls.member.id,
            'material_id': cls.material.id, 'cantidad': 10, 'uom': 'bolsa',
        })
        cls.corralon = cls.env['coop.corralon'].create({'name': 'Proveedor piloto'})
        cls.env['coop.lista.precio'].create({
            'corralon_id': cls.corralon.id, 'material_id': cls.material.id, 'precio': 100,
        })

    def test_member_cannot_validate_own_measurement(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.avance.with_user(self.user).action_validar()
        self.assertEqual(self.avance.state, 'borrador')
        self.assertEqual(self.item.cantidad_ejecutada, 0)

    def test_member_cannot_accept_own_request(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.pedido.with_user(self.user).write({'state': 'aceptado'})

    def test_member_cannot_register_own_unmeasured_work(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.otro.with_user(self.user).action_registrar()

    def test_member_cannot_map_own_work_to_validated_measurement(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.otro.with_user(self.user).action_mapear(self.item, 10)
        self.assertFalse(self.otro.avance_id)
        self.assertEqual(self.item.cantidad_ejecutada, 0)

    def test_coordinator_can_review_assigned_work(self):
        self.user.write({'groups_id': [(4, self.env.ref(
            'coop_members.group_coop_coordinador').id)]})
        self.obra.capataz_id = self.member
        self.avance.with_user(self.user).action_validar()
        self.pedido.with_user(self.user).action_aceptar()
        self.assertEqual(self.item.cantidad_ejecutada, 10)
        self.assertEqual(self.pedido.state, 'aceptado')

    def test_coordinator_cannot_review_own_draft_outside_assigned_work(self):
        self.user.write({'groups_id': [(4, self.env.ref(
            'coop_members.group_coop_coordinador').id)]})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.avance.with_user(self.user).action_validar()

    def test_worker_cannot_move_submission_to_another_work(self):
        other = self.env['project.project'].create({'name': 'Otra obra', 'is_coop_obra': True})
        item = self.item.copy({'obra_id': other.id})
        for record, values in [
                (self.avance, {'foja_item_id': item.id}),
                (self.pedido, {'obra_id': other.id}),
                (self.otro, {'obra_id': other.id})]:
            with self.assertRaises(AccessError), self.cr.savepoint():
                record.with_user(self.user).write(values)

    def test_worker_cannot_create_request_on_another_work(self):
        other = self.env['project.project'].create({'name': 'Otra obra', 'is_coop_obra': True})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['coop.pedido.material'].with_user(self.user).create({
                'obra_id': other.id, 'member_id': self.member.id,
                'material_id': self.material.id, 'cantidad': 10,
            })

    def test_worker_cannot_inject_review_via_context_defaults(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['coop.pedido.material'].with_user(self.user).with_context(
                default_revisado_por=self.member.id).create({
                    'obra_id': self.obra.id, 'member_id': self.member.id,
                    'material_id': self.material.id, 'cantidad': 10,
                })

    def test_worker_can_still_edit_draft_quantities(self):
        self.avance.with_user(self.user).write({'cantidad': 12})
        self.pedido.with_user(self.user).write({'cantidad': 12})
        self.assertEqual(self.avance.cantidad, 12)
        self.assertEqual(self.pedido.cantidad, 12)

    def test_mapped_work_cannot_be_reopened_and_counted_twice(self):
        self.otro.action_mapear(self.item, 10)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.otro.action_registrar()
        with self.assertRaises(UserError), self.cr.savepoint():
            self.otro.write({'state': 'pendiente'})
        self.assertEqual(self.item.cantidad_ejecutada, 10)

    def test_optimizer_rejects_pending_request(self):
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env['coop.orden.corralon'].generar_desde_pedidos(self.obra, self.pedido)
        self.assertFalse(self.pedido.orden_id)

    def test_optimizer_does_not_order_twice(self):
        self.pedido.action_aceptar()
        ordenes = self.env['coop.orden.corralon']
        first = ordenes.generar_desde_pedidos(self.obra, self.pedido)['ordenes'][0]
        with self.assertRaises(UserError), self.cr.savepoint():
            ordenes.generar_desde_pedidos(self.obra, self.pedido)
        self.assertEqual(self.pedido.orden_id, first)
        self.assertEqual(len(first.linea_ids), 1)

    def test_optimizer_rejects_request_from_another_work(self):
        other = self.env['project.project'].create({'name': 'Otra obra', 'is_coop_obra': True})
        self.pedido.action_aceptar()
        with self.assertRaises(UserError), self.cr.savepoint():
            self.env['coop.orden.corralon'].generar_desde_pedidos(other, self.pedido)
        self.assertFalse(self.pedido.orden_id)
