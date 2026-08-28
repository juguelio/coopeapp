"""Firma con hash del certificado de avance (`coop.certificado`).

El certificado se firma sobre el HASH de su contenido (obra, número, avance,
monto, fecha). Si después alguien cambia un número, `firma_valida` pasa a
False y se nota.

Este test existe para que el mixin `coop.firmable` quede cubierto también por
el lado de los certificados: sin él, romper el chequeo del hash a propósito no
ponía en rojo ningún test de este modelo (solo los del acta y la constancia).
"""

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCertificadoFirma(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env['res.partner'].create({'name': 'Sindico Cert'})
        cls.sindico = cls.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': 'Sindico Cert', 'dni': '28999111',
                'partner_id': partner.id})
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra Certificados', 'is_coop_obra': True})
        cls.cert = cls.env['coop.certificado'].create({
            'name': 'Certificado 1', 'obra_id': cls.obra.id, 'numero': 1,
            'porcentaje_avance': 20.0, 'monto_certificado': 500000.0,
            'date': '2026-08-01'})

    def test_firmar_registra_quien_cuando_y_el_hash(self):
        self.assertFalse(self.cert.firmado)
        self.assertFalse(self.cert.firma_valida)
        self.cert.action_firmar(member=self.sindico)
        self.assertTrue(self.cert.firmado)
        self.assertEqual(self.cert.firmado_por_id, self.sindico)
        self.assertTrue(self.cert.fecha_firma)
        self.assertTrue(self.cert.hash_firma)
        self.assertTrue(self.cert.firma_valida, 'recién firmada tiene que valer')

    def test_cambiar_el_monto_invalida_la_firma(self):
        self.cert.action_firmar(member=self.sindico)
        self.assertTrue(self.cert.firma_valida)
        hash_firmado = self.cert.hash_firma

        self.cert.write({'monto_certificado': 999999.0})

        self.assertFalse(self.cert.firma_valida,
                         'cambiar el monto tiene que romper la firma')
        self.assertEqual(self.cert.hash_firma, hash_firmado,
                         'el hash firmado no se reescribe solo')
        self.assertNotEqual(self.cert.hash_actual, hash_firmado)

    def test_cambiar_algo_fuera_del_hash_no_rompe_la_firma(self):
        self.cert.action_firmar(member=self.sindico)
        self.cert.write({'notes': 'Observación agregada después de firmar'})
        self.assertTrue(self.cert.firma_valida)
