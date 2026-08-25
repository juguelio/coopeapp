"""Constancia de entrega firmada de herramientas (P5a fase 2).

Una herramienta prestada afuera se reclama con un papel. Sin constancia, la
discusión es la memoria de uno contra la del otro. Y una constancia que se
puede editar después de firmada no es una constancia: es un texto.

Por eso lo que se firma es el HASH del contenido, igual que en
`coop.certificado` y en el acta. Estos tests prueban las dos mitades: que la
firma se registre, y —lo que importa— que se INVALIDE si alguien cambia
después a quién se la prestó o hasta cuándo.
"""

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConstanciaEntrega(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env['res.partner'].create({'name': 'Socio Herramienta'})
        cls.socio = cls.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': 'Socio Herramienta', 'dni': '32777888',
                'partner_id': partner.id})
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra Herramientas', 'is_coop_obra': True})
        cls.herramienta = cls.env['maintenance.equipment'].create({
            'name': 'Hormigonera 150L', 'codigo_etiqueta': 'H-001',
            'valor_reposicion': 850000.0})

    def _prestamo(self, **extra):
        vals = {
            'equipment_id': self.herramienta.id, 'tipo': 'externo',
            'prestado_a': 'Estudio Ruffolo', 'prestado_doc': '20-11222333-9',
            'prestado_tel': '2944500999',
            'fecha_retiro': '2026-08-20',
            'fecha_devolucion_prevista': '2026-08-30',
            'member_id': self.socio.id,
        }
        vals.update(extra)
        return self.env['coop.asignacion.herramienta'].create(vals)

    # ── la constancia dice lo que salió ──────────────────────────────
    def test_la_constancia_nombra_lo_entregado_y_a_quien(self):
        a = self._prestamo()
        texto = a.constancia_texto
        self.assertIn('Hormigonera 150L', texto)
        self.assertIn('H-001', texto)
        self.assertIn('Estudio Ruffolo', texto)
        self.assertIn('20-11222333-9', texto)
        self.assertIn('2026-08-30', texto, 'tiene que decir hasta cuándo')
        self.assertIn('Sin firmar', texto)

    # ── firmar ───────────────────────────────────────────────────────
    def test_firmar_registra_quien_cuando_y_el_hash(self):
        a = self._prestamo()
        self.assertFalse(a.firmado)
        self.assertFalse(a.firma_valida)
        a.action_firmar_constancia(member=self.socio)
        self.assertTrue(a.firmado)
        self.assertEqual(a.firmado_por_id, self.socio)
        self.assertTrue(a.fecha_firma)
        self.assertTrue(a.hash_firma)
        self.assertTrue(a.firma_valida, 'recién firmada tiene que valer')
        self.assertIn('Firmada por Socio Herramienta', a.constancia_texto)

    # ── LO QUE IMPORTA: la firma se cae si se toca lo firmado ────────
    def test_cambiar_a_quien_se_presto_invalida_la_firma(self):
        a = self._prestamo()
        a.action_firmar_constancia(member=self.socio)
        self.assertTrue(a.firma_valida)
        hash_firmado = a.hash_firma

        a.write({'prestado_a': 'Otro Estudio'})

        self.assertFalse(a.firma_valida,
                         'cambiar el destinatario tiene que romper la firma')
        self.assertEqual(a.hash_firma, hash_firmado,
                         'el hash firmado no se reescribe solo')
        self.assertNotEqual(a.hash_actual, hash_firmado)
        self.assertIn('ya no vale', a.constancia_texto)

    def test_cambiar_la_fecha_de_devolucion_invalida_la_firma(self):
        """Correr la fecha de devolución después de firmar es exactamente la
        discusión que la constancia existe para evitar."""
        a = self._prestamo()
        a.action_firmar_constancia(member=self.socio)
        a.write({'fecha_devolucion_prevista': '2026-12-31'})
        self.assertFalse(a.firma_valida)

    def test_cambiar_algo_no_firmado_no_rompe_la_firma(self):
        """El teléfono no entra en el hash: corregirlo no puede invalidar una
        entrega que sí ocurrió. Si todo invalidara la firma, nadie la usaría."""
        a = self._prestamo()
        a.action_firmar_constancia(member=self.socio)
        a.write({'prestado_tel': '2944511111'})
        self.assertTrue(a.firma_valida)

    # ── no se firma cualquier cosa ───────────────────────────────────
    def test_no_se_firma_una_devolucion(self):
        a = self._prestamo()
        a.action_devolver()
        with self.assertRaises(UserError) as cm:
            a.action_firmar_constancia(member=self.socio)
        self.assertIn('ya volvió', str(cm.exception))
        self.assertFalse(a.firmado)

    def test_una_salida_a_obra_tambien_lleva_constancia(self):
        a = self._prestamo(tipo='obra', obra_id=self.obra.id,
                           prestado_a=False, prestado_doc=False)
        self.assertIn('Obra Herramientas', a.constancia_texto)
        self.assertIn('Socio Herramienta', a.constancia_texto)
        a.action_firmar_constancia(member=self.socio)
        self.assertTrue(a.firma_valida)
