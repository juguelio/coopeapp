"""El contrato llega DESPUÉS de la obra y reconcilia, no pisa.

Germán (28/08): "arreglamos de palabra, empezamos la obra y luego acomodamos
los contratos". Las fechas de palabra (`fecha_inicio` / `fecha_fin`) mandan
para el CPM y el `atraso_dias` desde el día 1. Cuando llega el papel firmado,
sus fechas se cargan aparte y solo se muestran si divergen: nunca pisan las
operativas.
"""

from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestContratoEstado(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra palabra/firmado', 'is_coop_obra': True})
        cls.comitente = cls.env['res.partner'].create({'name': 'Municipio Y'})
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

    def _contrato(self, **extra):
        vals = {
            'name': 'C-1', 'obra_id': self.obra.id,
            'comitente_id': self.comitente.id,
            'fecha_inicio': '2026-01-01', 'fecha_fin': '2026-01-21',
        }
        vals.update(extra)
        return self.env['coop.contrato'].create(vals)

    def test_contrato_de_palabra_calcula_el_atraso_desde_el_dia_1(self):
        """Sin documento y sin fechas firmadas, el CPM ya tiene contra qué
        comparar: fin a 20 días, CPM 26 días -> 6 de atraso."""
        contrato = self._contrato()
        self.assertEqual(contrato.estado, 'palabra')
        self.assertFalse(contrato.documento)
        self.assertFalse(contrato.fechas_divergen)

        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.fecha_fin_contractual, date(2026, 1, 21))
        self.assertEqual(self.obra.fin_obra_estimado, date(2026, 1, 27))
        self.assertEqual(self.obra.atraso_dias, 6)

    def test_firmado_con_fechas_iguales_no_diverge_ni_mueve_el_atraso(self):
        contrato = self._contrato()
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.atraso_dias, 6)

        contrato.write({
            'estado': 'firmado',
            'fecha_inicio_firmado': '2026-01-01',
            'fecha_fin_firmado': '2026-01-21',
        })
        self.assertFalse(contrato.fechas_divergen)
        self.assertEqual(self.obra.fecha_fin_contractual, date(2026, 1, 21))
        self.assertEqual(self.obra.atraso_dias, 6)

    def test_firmado_con_fecha_distinta_diverge_pero_el_atraso_no_cambia(self):
        contrato = self._contrato()
        self.obra.action_calcular_ruta_critica()
        self.assertEqual(self.obra.atraso_dias, 6)

        # El papel dice fin a 60 días: si esto pisara la fecha de palabra,
        # el atraso pasaría a adelanto. No debe pasar.
        contrato.write({
            'estado': 'firmado',
            'fecha_fin_firmado': '2026-03-02',
        })
        self.assertTrue(contrato.fechas_divergen)
        self.assertEqual(self.obra.fecha_fin_contractual, date(2026, 1, 21))
        self.assertEqual(self.obra.fin_obra_estimado, date(2026, 1, 27))
        self.assertEqual(self.obra.atraso_dias, 6)

    def test_control_la_fecha_firmada_nunca_pisa_la_de_palabra(self):
        """Canario. Si alguien engancha el CPM / `atraso_dias` a las fechas
        firmadas, este test se pone en rojo: reintroduce el bug de timing que
        el patch P2 viene a arreglar."""
        contrato = self._contrato(
            estado='firmado', fecha_fin_firmado='2026-06-01')
        self.obra.action_calcular_ruta_critica()

        # La obra reconcilia contra la fecha de PALABRA, no la del papel.
        self.assertEqual(self.obra.fecha_fin_contractual,
                         contrato.fecha_fin)
        self.assertNotEqual(self.obra.fecha_fin_contractual,
                            contrato.fecha_fin_firmado)
        self.assertEqual(self.obra.atraso_dias, 6)
        # Si el atraso se calculara contra el papel, sería adelanto (< 0).
        self.assertGreater(self.obra.atraso_dias, 0)
