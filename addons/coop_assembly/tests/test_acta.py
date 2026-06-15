from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestActaFirma(TransactionCase):
    """M5: el acta legal se genera y la firma se invalida si el acta cambia."""

    def test_acta_genera_y_firma_se_invalida(self):
        pres = self.env['coop.member'].create({
            'name': 'Presi', 'dni': '25111000', 'cuil': '20-25111000-1',
            'role': 'board'})
        secre = self.env['coop.member'].create({
            'name': 'Secre', 'dni': '25111001', 'cuil': '27-25111001-2',
            'role': 'board'})
        asamblea = self.env['coop.assembly'].create({
            'name': 'Asamblea Test', 'assembly_type': 'ordinary',
            'date': '2026-03-15 18:00:00',
            'president_id': pres.id, 'secretary_id': secre.id,
            'attendee_ids': [(6, 0, [pres.id, secre.id])]})
        self.env['coop.assembly.point'].create({
            'assembly_id': asamblea.id, 'sequence': 1,
            'name': 'Punto uno', 'resolucion': 'Aprobado', 'state': 'resuelto'})

        asamblea.action_generate_minutes()
        self.assertTrue(asamblea.numero_acta, 'asigna número de acta')
        self.assertIn('ACTA N°', asamblea.acta_texto)
        self.assertTrue(asamblea.acta_hash, 'computa el hash')

        firma = asamblea.action_firmar(pres, 'presidente')
        self.assertTrue(firma.firma_valida, 'la firma recién hecha es válida')

        # si el acta cambia, la firma queda invalidada
        asamblea.acta_texto = (asamblea.acta_texto or '') + ' (modificado)'
        self.assertFalse(
            firma.firma_valida,
            'la firma debe invalidarse cuando el acta cambia')
