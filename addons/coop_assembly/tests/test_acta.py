from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestActaFirma(TransactionCase):
    """M5: el acta legal se genera y la firma se invalida si el acta cambia."""

    def _socio(self, name, dni, **extra):
        """Crea un socio con su contacto.

        `coop.member.partner_id` es required=True y `create()` no lo
        autocompleta. Estos tests lo omitían, así que nunca pudieron pasar.
        `skip_portal_user` evita dar de alta el usuario de la app, que no hace
        falta acá y hace los tests más lentos.
        """
        partner = self.env['res.partner'].create({'name': name})
        vals = {'name': name, 'dni': dni, 'partner_id': partner.id}
        vals.update(extra)
        return self.env['coop.member'].with_context(
            skip_portal_user=True).create(vals)

    def test_acta_genera_y_firma_se_invalida(self):
        pres = self._socio('Presi', '25111000', cuil='20-25111000-1',
                           role='board')
        secre = self._socio('Secre', '25111001', cuil='27-25111001-2',
                            role='board')
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

    def test_acta_sin_quorum_dice_la_verdad(self):
        """El acta no puede afirmar quórum cuando no lo hay (hallazgo 2026-08-20)."""
        members = self.env['coop.member'].browse()
        for i in range(4):
            members |= self._socio('M%d' % (i + 1), '2511100%d' % i,
                                   role='worker', state='active')
        asamblea = self.env['coop.assembly'].create({
            'name': 'Asamblea sin quórum', 'assembly_type': 'ordinary',
            'date': '2026-03-15 18:00:00',
            'president_id': members[0].id, 'secretary_id': members[1].id,
            'attendee_ids': [(6, 0, [members[0].id])]})
        self.assertFalse(asamblea.quorum_reached, '1 de 4 = 25% < 50%')
        asamblea.action_generate_minutes()
        self.assertIn('sin quórum suficiente', asamblea.acta_texto)
        self.assertNotIn('con quórum suficiente', asamblea.acta_texto)
        self.assertIn('no quedan firmes', asamblea.acta_texto)

    def test_acta_no_se_genera_con_votacion_abierta(self):
        """El acta no puede congelar el conteo de una votación en curso.

        Así nació el acta N° 2 de producción: dice "0 a favor, 1 en contra
        (rechazada)" sobre un punto donde el socio ve su voto a favor.
        """
        members = self.env['coop.member'].browse()
        for i in range(2):
            members |= self._socio('V%d' % (i + 1), '2522200%d' % i,
                                   role='board', state='active')
        asamblea = self.env['coop.assembly'].create({
            'name': 'Asamblea con votación en curso',
            'assembly_type': 'ordinary', 'date': '2026-03-15 18:00:00',
            'president_id': members[0].id, 'secretary_id': members[1].id,
            'attendee_ids': [(6, 0, members.ids)]})
        voto = self.env['coop.vote'].create({
            'assembly_id': asamblea.id, 'name': 'Compra de andamios nuevos',
            'state': 'open'})
        self.env['coop.assembly.point'].create({
            'assembly_id': asamblea.id, 'sequence': 1,
            'name': 'Andamios', 'vote_id': voto.id})

        with self.assertRaises(ValidationError):
            asamblea.action_generate_minutes()
        self.assertFalse(asamblea.acta_texto, 'no debe quedar acta a medio hacer')
        self.assertFalse(asamblea.numero_acta,
                         'tampoco debe consumir un número del libro')

        # cerrada, sí genera
        voto.action_close_vote()
        asamblea.action_generate_minutes()
        self.assertIn('ACTA N°', asamblea.acta_texto)

    def test_acta_no_se_genera_con_votacion_pendiente(self):
        """Una moción que nunca se abrió entra al acta como 0-0-0 y se lee
        'rechazada'. Nadie la rechazó: nadie la votó."""
        m = self._socio('V3', '25222002', role='board', state='active')
        asamblea = self.env['coop.assembly'].create({
            'name': 'Asamblea con moción sin abrir',
            'assembly_type': 'ordinary', 'date': '2026-03-15 18:00:00',
            'president_id': m.id, 'secretary_id': m.id,
            'attendee_ids': [(6, 0, [m.id])]})
        self.env['coop.vote'].create({
            'assembly_id': asamblea.id, 'name': 'Moción que nunca se abrió',
            'state': 'pending'})
        with self.assertRaises(ValidationError):
            asamblea.action_generate_minutes()
