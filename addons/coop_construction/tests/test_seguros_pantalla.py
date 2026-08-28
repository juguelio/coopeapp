"""Seguros — la parte que se ve: el helper del aviso y el onchange.

El cruce de fondo (`cobertura_faltante`) ya lo cubre `test_seguros.py`. Acá se
prueba lo que agregó la pantalla: `socios_sin_cobertura()` —el subconjunto que
alimenta el aviso al asignar plantel— y que el `onchange` avise sin bloquear.

La pregunta que estos tests protegen es la peligrosa: que al asignar a alguien
sin cobertura, la app lo DIGA en vez de dejar pasar el agujero en silencio,
que es exactamente lo que hoy hace la planilla.
"""

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSegurosPantalla(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = fields.Date.context_today(cls.env['coop.poliza'])
        cls.socio = cls._socio(cls, 'Diego Cobertura', '33444555')
        cls.jefe = cls._socio(cls, 'Yamila Central', '33444557')
        cls.obra = cls.env['project.project'].create({
            'name': 'Quintriqueo', 'is_coop_obra': True,
            'estado_obra': 'activa'})

    def setUp(self):
        super().setUp()
        self.obra.socio_obra_ids = [(6, 0, [self.socio.id])]

    def _socio(self, nombre, dni):
        partner = self.env['res.partner'].create({'name': nombre})
        return self.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': nombre, 'dni': dni, 'partner_id': partner.id})

    def _poliza_que_cubre(self, member):
        """Póliza general nominal, vigente, cuota confirmada, con el socio en
        la nómina desde hace un mes. Es el caso 'cubre = si'."""
        p = self.env['coop.poliza'].create({
            'numero': 'POL-001', 'sujeto': 'persona', 'tipo': 'general',
            'fecha_inicio': self.hoy - relativedelta(months=1),
            'fecha_fin': self.hoy + relativedelta(months=5),
        })
        adj = self.env['ir.attachment'].create({'name': 'c.pdf', 'raw': b'x'})
        self.env['coop.poliza.cuota'].create({
            'poliza_id': p.id, 'periodo': '2026-08',
            'vencimiento': self.hoy - relativedelta(days=5),
            'comprobante': adj.id, 'fecha_pago': self.hoy})
        self.env['coop.poliza.nomina'].create({
            'poliza_id': p.id, 'member_id': member.id,
            'fecha_alta': self.hoy - relativedelta(months=1)})
        p.invalidate_recordset()
        return p

    # ── el helper ────────────────────────────────────────────────────
    def test_asignado_sin_poliza_aparece_como_descubierto(self):
        """Sin ninguna póliza, el socio del plantel está sin cobertura."""
        sin = self.obra.socios_sin_cobertura()
        self.assertIn(self.socio, sin)

    def test_socio_cubierto_no_aparece(self):
        """Con póliza vigente y paga y el socio en nómina, no está descubierto.
        Es el control que hace que el test sepa distinguir: si esto también
        diera 'descubierto', el helper no probaría nada."""
        self._poliza_que_cubre(self.socio)
        sin = self.obra.socios_sin_cobertura()
        self.assertNotIn(self.socio, sin)

    def test_excepcion_vigente_saca_al_socio_de_la_lista(self):
        """Un arranque autorizado por escrito y vigente no es un descubierto:
        alguien se hizo cargo y hasta una fecha."""
        self.env['coop.cobertura.excepcion'].create({
            'obra_id': self.obra.id, 'member_id': self.socio.id,
            'motivo': 'Trámite en curso', 'autorizado_por_id': self.jefe.id,
            'fecha': self.hoy - relativedelta(days=1),
            'vence_el': self.hoy + relativedelta(days=10),
        })
        sin = self.obra.socios_sin_cobertura()
        self.assertNotIn(self.socio, sin)

    def test_excepcion_vencida_no_lo_salva(self):
        """Una excepción que ya venció no cubre: el agujero volvió."""
        self.env['coop.cobertura.excepcion'].create({
            'obra_id': self.obra.id, 'member_id': self.socio.id,
            'motivo': 'Trámite viejo', 'autorizado_por_id': self.jefe.id,
            'fecha': self.hoy - relativedelta(days=30),
            'vence_el': self.hoy - relativedelta(days=1),
        })
        sin = self.obra.socios_sin_cobertura()
        self.assertIn(self.socio, sin)

    # ── el aviso (onchange, NO bloqueante) ───────────────────────────
    def test_onchange_avisa_cuando_hay_descubierto(self):
        aviso = self.obra._onchange_aviso_cobertura()
        self.assertTrue(aviso and aviso.get('warning'),
                        'tiene que devolver un warning')
        self.assertIn('Diego Cobertura', aviso['warning']['message'])

    def test_onchange_no_avisa_si_esta_cubierto(self):
        self._poliza_que_cubre(self.socio)
        aviso = self.obra._onchange_aviso_cobertura()
        self.assertFalse(aviso, 'cubierto: no hay nada que avisar')

    def test_onchange_calla_si_no_es_obra_coop(self):
        self.obra.is_coop_obra = False
        self.assertFalse(self.obra._onchange_aviso_cobertura())
