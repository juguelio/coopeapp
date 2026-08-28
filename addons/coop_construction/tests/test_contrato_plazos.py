"""El contrato le da fechas a la obra, y la ruta crítica dice cuánto atrasa.

La obra no tenía ninguna fecha: el CPM sabía "termina el día 26" pero no
contra qué compararlo. Con `fecha_inicio` y `fecha_fin` del contrato,
`atraso_dias` pasa a decir «6 días tarde contra el contrato».

Corte de Germán: del contrato salen monto, condiciones y fechas. Los montos
de certificación NO se tocan acá.
"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContratoPlazos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra con contrato', 'is_coop_obra': True})
        cls.comitente = cls.env['res.partner'].create({'name': 'Municipio X'})
        # cadena lineal: t1 (10 d) -> t2 (10 d) -> t3 (6 d) = 26 días
        cls.t1 = cls._tarea('Excavacion', 10)
        cls.t2 = cls._tarea('Estructura', 10, cls.t1)
        cls.t3 = cls._tarea('Terminaciones', 6, cls.t2)

    @classmethod
    def _tarea(cls, nombre, dias, previa=None):
        vals = {'name': nombre, 'project_id': cls.obra.id,
                'duracion_dias': dias}
        if previa:
            vals['depend_on_ids'] = [(4, previa.id)]
        return cls.env['project.task'].create(vals)

    def _contrato(self, inicio, fin):
        return self.env['coop.contrato'].create({
            'name': 'C-1', 'obra_id': self.obra.id,
            'comitente_id': self.comitente.id,
            'fecha_inicio': inicio, 'fecha_fin': fin})

    def test_obra_sin_contrato_sigue_igual_sin_atraso(self):
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.duracion_cpm_dias, 26.0)
        self.assertEqual(self.obra.atraso_dias, 0)
        self.assertFalse(self.obra.fin_obra_estimado)
        self.assertFalse(self.obra.fecha_fin_contractual)

    def test_cpm_termina_despues_del_contrato_es_atraso(self):
        # contrato: fin a 20 días del inicio. CPM: 26 días -> 6 de atraso.
        self._contrato('2026-01-01', '2026-01-21')
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.fin_obra_estimado, date(2026, 1, 27))
        self.assertEqual(self.obra.atraso_dias, 6)

    def test_cpm_termina_antes_del_contrato_es_adelanto(self):
        self._contrato('2026-01-01', '2026-03-01')  # 59 días de plazo
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.atraso_dias, 26 - 59)
        self.assertLess(self.obra.atraso_dias, 0)

    def test_recalcular_tras_cambiar_una_tarea_mueve_el_atraso(self):
        # Nota: cerrar una tarea NO cambia la duración total por diseño (los
        # días ya se consumieron; ver project_project.action_calcular_ruta_critica).
        # Lo que mueve el atraso es cambiar la duración de una tarea crítica.
        self._contrato('2026-01-01', '2026-01-21')
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.atraso_dias, 6)

        self.t2.duracion_dias = 15  # +5 días en el camino crítico
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.duracion_cpm_dias, 31.0)
        self.assertEqual(self.obra.atraso_dias, 11)

    def test_el_contrato_no_toca_la_certificacion(self):
        """Del contrato salen fechas y monto; los certificados siguen
        saliendo del avance medido, no del monto del contrato."""
        self._contrato('2026-01-01', '2026-06-01')
        self.assertEqual(self.obra.total_certificado, 0.0)
        cert = self.env['coop.certificado'].create({
            'name': 'Cert 1', 'obra_id': self.obra.id, 'numero': 1,
            'monto_certificado': 123456.0, 'date': '2026-02-01',
            'state': 'aprobado'})
        self.assertEqual(self.obra.total_certificado, cert.monto_certificado)
