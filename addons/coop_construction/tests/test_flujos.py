from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('post_install', '-at_install')
class TestFlujosCoop(TransactionCase):
    """Tests de los flujos críticos de coopeapp (M1–M6)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.env['coop.member'].create({
            'name': 'Test Socio', 'dni': '30111222',
            'cuil': '20-30111222-3', 'role': 'worker',
        })
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra Test', 'is_coop_obra': True,
            'capataz_id': cls.member.id,
        })
        cls.etapa = cls.env['coop.etapa'].create({
            'obra_id': cls.obra.id, 'numero': 1, 'name': 'Etapa 1',
            'state': 'en_curso', 'ingreso': 1000000.0,
        })
        cls.material = cls.env['coop.material'].create({
            'name': 'Cemento Test', 'uom': 'bolsa'})
        cls.corralon = cls.env['coop.corralon'].create({
            'name': 'Corralón Test', 'telefono': '5492944000000'})

    # ── M1: orden al corralón imputa gasto al entregar ───────────────
    def test_m1_orden_entregada_imputa_gasto(self):
        pedido = self.env['coop.pedido.material'].create({
            'obra_id': self.obra.id, 'member_id': self.member.id,
            'material_id': self.material.id, 'uom': 'bolsa', 'cantidad': 10,
            'state': 'aceptado', 'corralon_id': self.corralon.id})
        orden = self.env['coop.orden.corralon'].create({
            'corralon_id': self.corralon.id, 'obra_id': self.obra.id})
        pedido.orden_id = orden.id
        orden.importe_total = 50000.0
        gastos_antes = len(self.etapa.gasto_ids)
        orden.action_entregar()
        self.assertEqual(orden.estado, 'entregada')
        self.assertTrue(orden.gasto_id, 'debe crear el gasto')
        self.assertEqual(len(self.etapa.gasto_ids), gastos_antes + 1)
        self.assertEqual(orden.gasto_id.rubro, 'materiales')

    # ── M2: el optimizador elige el acopio más barato y reserva saldo ─
    def test_m2_optimizador_prefiere_acopio(self):
        acopio = self.env['coop.acopio'].create({
            'numero': 'A1', 'obra_id': self.obra.id,
            'corralon_id': self.corralon.id, 'monto_total': 1000000.0})
        self.env['coop.acopio.precio'].create({
            'acopio_id': acopio.id, 'material_id': self.material.id,
            'precio_congelado': 7000.0})
        self.env['coop.lista.precio'].create({
            'corralon_id': self.corralon.id, 'material_id': self.material.id,
            'precio': 11000.0})
        pedido = self.env['coop.pedido.material'].create({
            'obra_id': self.obra.id, 'member_id': self.member.id,
            'material_id': self.material.id, 'uom': 'bolsa', 'cantidad': 10,
            'state': 'aceptado'})
        res = self.env['coop.orden.corralon'].generar_desde_pedidos(
            self.obra, pedido)
        self.assertEqual(len(res['ordenes']), 1)
        linea = res['ordenes'][0].linea_ids[0]
        self.assertEqual(linea.fuente, 'acopio')
        self.assertEqual(linea.precio_unitario, 7000.0)
        # el saldo del acopio se reserva (10 * 7000)
        self.assertEqual(acopio.saldo, 1000000.0 - 70000.0)

    # ── M3: aprobar presupuesto crea obra + etapas, re-aprobar bloquea ─
    def test_m3_aprobar_crea_obra(self):
        cliente = self.env['res.partner'].create({'name': 'Cliente Test'})
        ot = self.env['coop.orden.trabajo'].create({
            'cliente_id': cliente.id, 'descripcion': 'Trabajo test'})
        self.env['coop.ot.etapa'].create({
            'orden_id': ot.id, 'sequence': 10, 'name': 'Etapa A'})
        pres = self.env['coop.presupuesto'].create({
            'orden_id': ot.id, 'tipo_factura': 'B'})
        self.env['coop.presupuesto.linea'].create({
            'presupuesto_id': pres.id, 'categoria': 'materiales',
            'name': 'Materiales', 'cantidad': 1, 'precio_unitario': 500000.0,
            'iva_alicuota': '21'})
        pres.action_aprobar()
        self.assertTrue(ot.obra_id, 'debe crear la obra')
        self.assertTrue(ot.obra_id.is_coop_obra)
        self.assertEqual(len(ot.obra_id.etapa_ids), 1)
        # re-aprobar un 2do presupuesto sobre la misma OT debe bloquear
        pres2 = self.env['coop.presupuesto'].create({
            'orden_id': ot.id, 'tipo_factura': 'B'})
        with self.assertRaises(UserError):
            pres2.action_aprobar()

    # ── M3: IVA factura B (incluido) calcula neto e IVA correctos ─────
    def test_m3_iva_factura_b(self):
        cliente = self.env['res.partner'].create({'name': 'Cliente B'})
        ot = self.env['coop.orden.trabajo'].create({'cliente_id': cliente.id})
        pres = self.env['coop.presupuesto'].create({
            'orden_id': ot.id, 'tipo_factura': 'B'})
        self.env['coop.presupuesto.linea'].create({
            'presupuesto_id': pres.id, 'categoria': 'materiales',
            'name': 'X', 'cantidad': 1, 'precio_unitario': 121000.0,
            'iva_alicuota': '21'})
        self.assertAlmostEqual(pres.total, 121000.0, places=2)
        self.assertAlmostEqual(pres.neto, 100000.0, places=2)
        self.assertAlmostEqual(pres.iva, 21000.0, places=2)

    # ── M4: incidente de material resuelto imputa la merma ───────────
    def test_m4_incidente_material_imputa_merma(self):
        inc = self.env['coop.incidente'].create({
            'tipo': 'rotura_material', 'obra_id': self.obra.id,
            'material_id': self.material.id, 'cantidad': 2,
            'valor_estimado': 30000.0, 'reportado_por': self.member.id})
        inc.action_resolver()
        self.assertEqual(inc.state, 'resuelto')
        self.assertTrue(inc.gasto_id, 'debe imputar la merma como gasto')
        self.assertEqual(inc.gasto_id.rubro, 'materiales')
        self.assertEqual(inc.gasto_id.importe, 30000.0)

    # ── P5a: préstamo de herramientas fuera de la cooperativa ────────
    def _herramienta(self, nombre='Amoladora Test'):
        return self.env['maintenance.equipment'].create({
            'name': nombre, 'estado_coop': 'disponible'})

    def test_p5a_prestamo_externo_sin_obra(self):
        """El caso que antes no se podía anotar: prestarle una herramienta al
        equipo de arquitectos, sin obra propia y sin socio que la reciba."""
        eq = self._herramienta()
        asig = self.env['coop.asignacion.herramienta'].create({
            'equipment_id': eq.id, 'tipo': 'externo',
            'prestado_a': 'Estudio Arquitectos', 'prestado_tel': '2944000111',
            'fecha_retiro': '2026-07-01',
            'fecha_devolucion_prevista': '2026-07-10',
        })
        self.assertEqual(asig.state, 'prestada',
                         'el state sigue al tipo aunque no se declare')
        self.assertEqual(eq.estado_coop, 'prestada_externo',
                         'la herramienta NO puede quedar disponible')
        self.assertFalse(asig.obra_id, 'la obra es opcional en un préstamo')
        self.assertTrue(asig.dias_afuera > 0)
        self.assertTrue(asig.vencida, 'venció el 10/07/2026')
        self.assertIn(asig, self.env['coop.asignacion.herramienta'].search(
            [('vencida', '=', True)]), 'tiene que ser buscable por vencida')

        asig.action_devolver()
        self.assertEqual(asig.state, 'devuelta')
        self.assertTrue(asig.fecha_devolucion)
        self.assertFalse(asig.vencida, 'devuelta ya no está vencida')
        self.assertEqual(eq.estado_coop, 'disponible')

    def test_p5a_prestamo_sin_responsable_no_se_puede(self):
        """Sacarle el required a obra_id abrió la puerta a una salida sin
        destino. La cierra el constraint, no el formulario."""
        eq = self._herramienta('Hidrolavadora Test')
        with self.assertRaises(ValidationError):
            self.env['coop.asignacion.herramienta'].create({
                'equipment_id': eq.id, 'tipo': 'externo', 'prestado_a': '  '})

    def test_p5a_salida_a_obra_sigue_necesitando_obra(self):
        eq = self._herramienta('Mixer Test')
        with self.assertRaises(ValidationError):
            self.env['coop.asignacion.herramienta'].create({
                'equipment_id': eq.id, 'tipo': 'obra',
                'member_id': self.member.id})

    def test_p5a_asignacion_a_obra_no_cambio(self):
        """El camino de siempre tiene que seguir funcionando igual."""
        eq = self._herramienta('Martillo Test')
        asig = self.env['coop.asignacion.herramienta'].create({
            'equipment_id': eq.id, 'obra_id': self.obra.id,
            'member_id': self.member.id})
        self.assertEqual(asig.tipo, 'obra')
        self.assertEqual(asig.state, 'en_obra')
        self.assertEqual(eq.estado_coop, 'en_obra')
        self.assertEqual(eq.obra_id, self.obra)
        asig.action_devolver()
        self.assertEqual(eq.estado_coop, 'disponible')
        self.assertFalse(eq.obra_id)
