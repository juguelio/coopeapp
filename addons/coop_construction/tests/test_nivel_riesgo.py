"""Alto riesgo: el bloqueo que hoy no existe, y SOLO en alto.

Germán (28/08): en la obra común "si la obra no tiene alto riesgo… el
compañero arranca igual"; en las de alto riesgo "hay lugares que sin la nomina
en mano no te dejan entrar".

`nivel_riesgo` introduce ese bloqueo (`@api.constrains`) y solo para 'alto'. En
'bajo' y 'medio' no cambia nada: sigue el aviso NO bloqueante de siempre
(`_onchange_aviso_cobertura`). La escapatoria sigue siendo la excepción
registrada de Germán: opcional en medio, obligatoria en alto.
"""

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestNivelRiesgo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hoy = fields.Date.context_today(cls.env['coop.poliza'])
        cls.socio = cls._socio('Beto Riesgo', '40111222')
        cls.autoriza = cls._socio('Nora Riesgo', '40111223')
        cls.obra = cls.env['project.project'].create({
            'name': 'Puente Alto', 'is_coop_obra': True,
            'estado_obra': 'activa'})

    @classmethod
    def _socio(cls, nombre, dni):
        partner = cls.env['res.partner'].create({'name': nombre})
        return cls.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': nombre, 'dni': dni, 'partner_id': partner.id})

    def _asignar(self, *members):
        self.obra.socio_obra_ids = [(6, 0, [m.id for m in members])]
        self.obra.flush_recordset()

    def _poliza_que_cubre(self, member):
        p = self.env['coop.poliza'].create({
            'numero': 'POL-AR', 'sujeto': 'persona', 'tipo': 'general',
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

    def _excepcion(self, vence_dias, desde_dias=1):
        return self.env['coop.cobertura.excepcion'].create({
            'obra_id': self.obra.id, 'member_id': self.socio.id,
            'motivo': 'Trámite de alta en curso',
            'autorizado_por_id': self.autoriza.id,
            'fecha': self.hoy - relativedelta(days=desde_dias),
            'vence_el': self.hoy + relativedelta(days=vence_dias)})

    # ── bajo y medio: nada cambia, el piloto no se toca ──────────────
    def test_medio_sin_cobertura_guarda_igual(self):
        self.obra.nivel_riesgo = 'medio'
        self._asignar(self.socio)
        self.assertIn(self.socio, self.obra.socio_obra_ids)

    def test_bajo_sin_cobertura_guarda_igual(self):
        self.obra.nivel_riesgo = 'bajo'
        self._asignar(self.socio)
        self.assertIn(self.socio, self.obra.socio_obra_ids)

    def test_default_es_medio(self):
        self.assertEqual(
            self.env['project.project'].create({
                'name': 'X', 'is_coop_obra': True}).nivel_riesgo, 'medio')

    # ── alto: bloqueo duro, con la excepción como escapatoria ────────
    def test_alto_sin_cobertura_sin_excepcion_bloquea(self):
        self.obra.nivel_riesgo = 'alto'
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._asignar(self.socio)

    def test_alto_con_excepcion_vigente_guarda(self):
        self.obra.nivel_riesgo = 'alto'
        self._excepcion(vence_dias=15)
        self._asignar(self.socio)
        self.assertIn(self.socio, self.obra.socio_obra_ids)

    def test_alto_con_excepcion_vencida_bloquea(self):
        self.obra.nivel_riesgo = 'alto'
        self._excepcion(vence_dias=-10, desde_dias=40)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._asignar(self.socio)

    def test_alto_con_socio_cubierto_guarda_sin_ruido(self):
        self.obra.nivel_riesgo = 'alto'
        self._poliza_que_cubre(self.socio)
        self._asignar(self.socio)
        self.assertIn(self.socio, self.obra.socio_obra_ids)

    def test_alto_pasar_a_alto_con_plantel_descubierto_bloquea(self):
        """El constraint también mira `nivel_riesgo`: subir una obra ya poblada
        a 'alto' no puede dejar pasar un plantel sin cobertura."""
        self.obra.nivel_riesgo = 'medio'
        self._asignar(self.socio)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.obra.nivel_riesgo = 'alto'
            self.obra.flush_recordset()

    # ── canario ─────────────────────────────────────────────────────
    def test_control_el_bloqueo_es_solo_de_alto(self):
        """Canario. El piloto no se puede romper: en 'medio' este mismo caso
        —socio sin cobertura, sin excepción— tiene que SEGUIR guardando; en
        'alto' tiene que romper. Si alguien hace que el constraint aplique a
        'medio', o que deje de aplicar a 'alto', este test se pone en rojo."""
        self.obra.nivel_riesgo = 'medio'
        self._asignar(self.socio)
        self.assertIn(self.socio, self.obra.socio_obra_ids)

        self.obra.socio_obra_ids = [(5, 0, 0)]
        self.obra.nivel_riesgo = 'alto'
        self.obra.flush_recordset()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._asignar(self.socio)
