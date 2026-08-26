"""Seguros: que el cruce diga la verdad, y que diga "no sé" cuando no sabe.

Lo que se prueba acá no es que el modelo guarde pólizas. Es que conteste bien
la única pregunta que importa —¿esta persona puede trabajar en esta obra hoy?—
y sobre todo que **no afirme cobertura que no puede probar**.

Una app que dice "cubierto" y se equivoca es peor que no tener app: reemplaza
una preocupación real por una tranquilidad falsa, y esta vez la afirmación
falsa manda a alguien a un andamio.
"""

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSeguros(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = fields.Date.context_today(cls.env['coop.poliza'])
        cls.socio = cls._socio(cls, 'Diego Cobertura', '33444555')
        cls.otro = cls._socio(cls, 'Ana Cobertura', '33444556')
        cls.obra = cls.env['project.project'].create({
            'name': 'Quintriqueo', 'is_coop_obra': True,
            'estado_obra': 'activa'})

    def setUp(self):
        super().setUp()
        # El plantel se arma en cada test y no en setUpClass a propósito.
        # Un `assertRaises` sobre un create que viola constraint deja el
        # cursor de Postgres en estado de error, y el rollback de ese
        # savepoint se llevaba puesto el estado compartido de la clase: el
        # cruce corría contra un plantel vacío y devolvía "ningún problema",
        # que es la falla más peligrosa posible en este módulo.
        self.obra.socio_obra_ids = [(6, 0, [self.socio.id])]

    def _socio(self, nombre, dni):
        partner = self.env['res.partner'].create({'name': nombre})
        return self.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': nombre, 'dni': dni, 'partner_id': partner.id})

    def _poliza(self, **extra):
        """Póliza general nominal, vigente, con la cuota confirmada."""
        vals = {
            'numero': 'POL-001', 'sujeto': 'persona', 'tipo': 'general',
            'fecha_inicio': self.hoy - relativedelta(months=1),
            'fecha_fin': self.hoy + relativedelta(months=5),
        }
        vals.update(extra)
        p = self.env['coop.poliza'].create(vals)
        return p

    def _cuota_paga(self, poliza, dias=-5):
        adj = self.env['ir.attachment'].create({
            'name': 'comprobante.pdf', 'raw': b'x'})
        return self.env['coop.poliza.cuota'].create({
            'poliza_id': poliza.id, 'periodo': '2026-08',
            'vencimiento': self.hoy + relativedelta(days=dias),
            'comprobante': adj.id, 'fecha_pago': self.hoy})

    def _en_nomina(self, poliza, member, alta=None, baja=None):
        return self.env['coop.poliza.nomina'].create({
            'poliza_id': poliza.id, 'member_id': member.id,
            'fecha_alta': alta or (self.hoy - relativedelta(months=1)),
            'fecha_baja': baja})

    # ── el caso peligroso: vigente PERO impaga ───────────────────────
    def test_vigente_con_cuota_vencida_NO_cubre(self):
        """El cuadrante de arriba a la derecha: dentro de vigencia y sin pagar.
        Es el que un solo campo `state` esconde."""
        p = self._poliza()
        self.env['coop.poliza.cuota'].create({
            'poliza_id': p.id, 'periodo': '2026-07',
            'vencimiento': self.hoy - relativedelta(days=10)})
        p.invalidate_recordset()
        self.assertTrue(p.vigente, 'está dentro del plazo')
        self.assertEqual(p.estado_pago, 'vencido')
        self.assertEqual(p.cubre, 'no', 'vigente e impaga NO cubre')
        self.assertIn('impaga no cubre', p.motivo_cobertura)

    def test_sin_comprobante_dice_no_se_y_no_dice_que_cubre(self):
        """La app nunca infiere "pago" de la ausencia de información."""
        p = self._poliza()
        self.env['coop.poliza.cuota'].create({
            'poliza_id': p.id, 'periodo': '2026-08',
            'vencimiento': self.hoy})
        p.invalidate_recordset()
        self.assertEqual(p.estado_pago, 'sin_confirmar')
        self.assertEqual(p.cubre, 'no_se')
        self.assertIn('No sabemos', p.motivo_cobertura)

    def test_sin_cuotas_cargadas_tampoco_afirma_cobertura(self):
        p = self._poliza()
        self.assertEqual(p.cubre, 'no_se',
                         'sin cuotas no se puede afirmar que se está pagando')

    def test_fuera_de_vigencia_no_cubre(self):
        p = self._poliza(fecha_inicio=self.hoy - relativedelta(months=8),
                         fecha_fin=self.hoy - relativedelta(days=1))
        self._cuota_paga(p)
        p.invalidate_recordset()
        self.assertFalse(p.vigente)
        self.assertEqual(p.cubre, 'no')

    def test_vigente_y_paga_si_cubre(self):
        p = self._poliza()
        self._cuota_paga(p)
        p.invalidate_recordset()
        self.assertEqual(p.cubre, 'si')

    def test_una_fecha_de_pago_sin_comprobante_no_alcanza(self):
        """Confirmado exige archivo Y fecha. Una fecha sola es alguien
        diciendo que pagó."""
        p = self._poliza()
        c = self.env['coop.poliza.cuota'].create({
            'poliza_id': p.id, 'periodo': '2026-08',
            'vencimiento': self.hoy - relativedelta(days=3),
            'fecha_pago': self.hoy})
        self.assertNotEqual(c.estado, 'confirmado')

    # ── la nómina responde por fecha, no solo por hoy ────────────────
    def test_la_nomina_contesta_si_estaba_cubierto_ese_dia(self):
        """La pregunta del día del accidente es "¿estaba en la nómina
        entonces?", y darlo de baja hoy no puede borrar que estuvo."""
        p = self._poliza()
        self._cuota_paga(p)
        baja = self.hoy - relativedelta(days=10)
        self._en_nomina(p, self.socio,
                        alta=self.hoy - relativedelta(months=1), baja=baja)
        antes = self.hoy - relativedelta(days=20)
        self.assertTrue(p.cubre_a(self.socio, antes),
                        'estaba en la nómina hace 20 días')
        self.assertFalse(p.cubre_a(self.socio, self.hoy),
                         'ya no está hoy')

    def test_quien_nunca_estuvo_en_la_nomina_no_esta_cubierto(self):
        p = self._poliza()
        self._cuota_paga(p)
        self._en_nomina(p, self.socio)
        self.assertFalse(p.cubre_a(self.otro))

    # ── EL CRUCE, que es la función ──────────────────────────────────
    def test_el_cruce_nombra_a_la_persona_y_la_obra(self):
        """La prueba de que el proyecto está hecho es que produzca esta frase
        sola: «Diego López está asignado a Quintriqueo y no figura en la
        póliza.»"""
        p = self._poliza()
        self._cuota_paga(p)
        # la póliza existe y está paga, pero el socio NO está en la nómina
        problemas = self.obra.cobertura_faltante()
        sin_cobertura = [x for x in problemas if x['tipo'] == 'sin_cobertura']
        self.assertEqual(len(sin_cobertura), 1)
        texto = sin_cobertura[0]['texto']
        self.assertIn('Diego Cobertura', texto)
        self.assertIn('Quintriqueo', texto)
        self.assertIn('no figura en la póliza', texto)

    def test_si_esta_en_la_nomina_el_cruce_no_lo_reporta(self):
        p = self._poliza()
        self._cuota_paga(p)
        self._en_nomina(p, self.socio)
        problemas = self.obra.cobertura_faltante()
        self.assertFalse([x for x in problemas if x['tipo'] == 'sin_cobertura'])

    def test_en_la_nomina_pero_con_la_poliza_impaga_igual_se_reporta(self):
        """Estar en la lista no alcanza si la póliza no cubre. Este es el
        cruce de los dos ejes, que es donde vive el riesgo real."""
        p = self._poliza()
        self.env['coop.poliza.cuota'].create({
            'poliza_id': p.id, 'periodo': '2026-07',
            'vencimiento': self.hoy - relativedelta(days=10)})
        self._en_nomina(p, self.socio)
        p.invalidate_recordset()
        problemas = self.obra.cobertura_faltante()
        self.assertTrue([x for x in problemas if x['tipo'] == 'sin_cobertura'],
                        'la póliza está impaga: no cubre aunque esté en la lista')

    # ── la excepción registrada ──────────────────────────────────────
    def test_la_excepcion_no_esconde_el_problema_lo_atribuye(self):
        """Germán: «a veces hacemos que arranque igual hasta que salga el
        trámite pero nosotros asumimos el riesgo». La app no lo tapa: deja
        asentado quién se hizo cargo y hasta cuándo."""
        self._poliza()
        self.env['coop.cobertura.excepcion'].create({
            'obra_id': self.obra.id, 'member_id': self.socio.id,
            'motivo': 'Trámite de alta en curso',
            'autorizado_por_id': self.otro.id,
            'vence_el': self.hoy + relativedelta(days=15)})
        problemas = self.obra.cobertura_faltante()
        excepciones = [x for x in problemas if x['tipo'] == 'excepcion']
        self.assertEqual(len(excepciones), 1, 'sigue apareciendo, no desaparece')
        texto = excepciones[0]['texto']
        self.assertIn('Ana Cobertura', texto, 'dice quién asumió el riesgo')
        self.assertIn('Trámite de alta en curso', texto)
        self.assertFalse([x for x in problemas if x['tipo'] == 'sin_cobertura'])

    def test_una_excepcion_vencida_no_sirve_de_nada(self):
        """Una excepción sin vencimiento sería un permiso permanente. Vencida,
        el problema vuelve a aparecer como lo que es."""
        self._poliza()
        self.env['coop.cobertura.excepcion'].create({
            'obra_id': self.obra.id, 'member_id': self.socio.id,
            'motivo': 'Trámite viejo', 'autorizado_por_id': self.otro.id,
            'fecha': self.hoy - relativedelta(days=40),
            'vence_el': self.hoy - relativedelta(days=10)})
        problemas = self.obra.cobertura_faltante()
        self.assertTrue([x for x in problemas if x['tipo'] == 'sin_cobertura'],
                        'la excepción venció: vuelve a ser un problema')

    def test_la_excepcion_necesita_fecha_de_vencimiento(self):
        with self.assertRaises(Exception), self.cr.savepoint():
            self.env['coop.cobertura.excepcion'].create({
                'obra_id': self.obra.id, 'member_id': self.socio.id,
                'motivo': 'sin fecha', 'autorizado_por_id': self.otro.id})

    # ── requisitos de la obra ────────────────────────────────────────
    def test_un_requisito_sin_poliza_se_reporta(self):
        self.env['coop.poliza.requisito'].create({
            'obra_id': self.obra.id, 'tipo_requerido': 'altura',
            'exigido_por': 'comitente'})
        problemas = self.obra.cobertura_faltante()
        req = [x for x in problemas if x['tipo'] == 'requisito']
        self.assertEqual(len(req), 1)
        self.assertIn('altura', req[0]['texto'].lower())

    def test_un_no_se_NO_satisface_un_requisito(self):
        """El caso más importante del módulo: una póliza sobre la que no
        sabemos si está paga no habilita a nadie."""
        p = self._poliza()   # vigente pero sin cuotas => 'no_se'
        r = self.env['coop.poliza.requisito'].create({
            'obra_id': self.obra.id, 'tipo_requerido': 'altura',
            'poliza_id': p.id})
        self.assertEqual(p.cubre, 'no_se')
        self.assertFalse(r.satisfecho,
                         'un "no sabemos" no puede habilitar trabajo en altura')

    def test_un_requisito_con_poliza_que_cubre_si_se_satisface(self):
        p = self._poliza(tipo='altura')
        self._cuota_paga(p)
        p.invalidate_recordset()
        r = self.env['coop.poliza.requisito'].create({
            'obra_id': self.obra.id, 'tipo_requerido': 'altura',
            'poliza_id': p.id})
        self.assertTrue(r.satisfecho)

    # ── coherencia del modelo ────────────────────────────────────────
    def test_una_poliza_de_obra_necesita_obra(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._poliza(sujeto='obra', tipo='caucion')

    def test_el_cruce_diario_recorre_las_obras_activas(self):
        self._poliza()
        problemas = self.env['project.project'].cruce_diario_cobertura()
        self.assertTrue(
            any(x.get('member') and x['member'].id == self.socio.id
                for x in problemas),
            'la obra activa tiene que entrar en el cruce diario')
