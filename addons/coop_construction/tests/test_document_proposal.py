from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDocumentProposal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.aseguradora = cls.env['res.partner'].create({
            'name': 'Patagonia Seguros Demo',
        })
        cls.obra = cls.env['project.project'].create({
            'name': 'Obra demo aprobación',
            'is_coop_obra': True,
            'estado_obra': 'activa',
        })

    def _socio(self, nombre, dni):
        partner = self.env['res.partner'].create({'name': nombre})
        return self.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': nombre, 'dni': dni, 'partner_id': partner.id})

    def payload(self):
        return {
            'source': {
                'file_id': '2438121470111',
                'version_id': '2703223890911',
                'file_name': 'POLIZA-DEMO-QUINTRIQUEO.pdf',
                'sha256': 'demo-sha256',
            },
            'proposal': {
                'numero': 'DEMO-2026-001',
                'aseguradora': 'Patagonia Seguros Demo',
                'obra': 'Quintriqueo',
                'fecha_inicio': '2026-09-01',
                'fecha_fin': '2027-08-31',
                'importe': 185000.0,
                'socios': ['Diego López', 'María González', 'Pablo Castillo'],
            },
            'conflicts': [],
        }

    def _payload_nomina(self, socios):
        """Payload de una póliza nominal con los socios a cubrir y vigencia
        relativa a hoy (para que quede dentro del plazo al aprobar)."""
        hoy = fields.Date.context_today(self.env['coop.poliza'])
        payload = self.payload()
        payload['proposal']['socios'] = socios
        payload['proposal']['fecha_inicio'] = (
            hoy - relativedelta(months=1)).isoformat()
        payload['proposal']['fecha_fin'] = (
            hoy + relativedelta(months=5)).isoformat()
        return payload

    def test_ingestion_is_pending_and_idempotent(self):
        model = self.env['coop.document.proposal']
        first = model.create_from_ingestion(self.payload())
        second = model.create_from_ingestion(self.payload())
        self.assertEqual(first, second)
        self.assertEqual(first.state, 'pending_review')
        self.assertFalse(first.approved_by_id)
        self.assertFalse(first.poliza_id)

    def test_cannot_approve_without_obra(self):
        proposal = self.env['coop.document.proposal'].create_from_ingestion(self.payload())
        with self.assertRaises(UserError):
            proposal.action_approve()
        self.assertEqual(proposal.state, 'pending_review')
        self.assertFalse(proposal.approved_by_id)

    def test_approval_records_authenticated_user_and_creates_policy(self):
        proposal = self.env['coop.document.proposal'].create_from_ingestion(self.payload())
        proposal.write({'obra_id': self.obra.id})
        proposal.action_approve()
        proposal.invalidate_recordset()
        self.assertEqual(proposal.state, 'approved')
        self.assertEqual(proposal.approved_by_id, self.env.user)
        self.assertEqual(proposal.reviewed_by_id, self.env.user)
        self.assertTrue(proposal.approved_at)
        self.assertTrue(proposal.reviewed_at)
        self.assertTrue(proposal.approved_by_role)
        self.assertEqual(proposal.poliza_id.numero, 'DEMO-2026-001')
        self.assertEqual(proposal.poliza_id.obra_id, self.obra)

    def test_aprobacion_crea_nomina_y_el_cruce_la_ve(self):
        """Aprobar una propuesta de póliza nominal tiene que poblar la nómina;
        En caso contrario, la póliza existe pero no cubre a nadie y el cruce de seguros
        reporta a todos como sin cobertura (demo verde, función muerta)."""
        dieg = self._socio('Diego López', '33444555')
        self._socio('María González', '33444556')
        proposal = self.env['coop.document.proposal'].create_from_ingestion(
            self._payload_nomina(['Diego López', 'María González']))
        proposal.write({'obra_id': self.obra.id})
        proposal.action_approve()
        proposal.invalidate_recordset()
        p = proposal.poliza_id
        self.assertEqual(p.sujeto, 'persona',
                         'una póliza nominal de gente se cruza por sujeto persona')
        self.assertEqual(len(p.nomina_ids), 2,
                         'los socios extraídos pasan a líneas de nómina')
        self.assertIn(dieg.id, p.nomina_ids.mapped('member_id.id'))
        self.assertTrue(p.cubre_a(dieg),
                        'vigente y en la nómina => cubre')

    def test_aprobacion_deja_pendiente_el_socio_sin_vincular(self):
        """Lo que no matchea exacto contra el padrón NO se adivina: queda
        pendiente de vincular para que un humano decida, no en blanco."""
        dieg = self._socio('Diego López', '33444555')
        proposal = self.env['coop.document.proposal'].create_from_ingestion(
            self._payload_nomina(['Diego López', 'Persona Inexistente']))
        proposal.write({'obra_id': self.obra.id})
        proposal.action_approve()
        proposal.invalidate_recordset()
        p = proposal.poliza_id
        self.assertEqual(len(p.nomina_ids), 1,
                         'solo se vincula lo que matchea exacto')
        self.assertIn(dieg.id, p.nomina_ids.mapped('member_id.id'))
        self.assertTrue(proposal.socios_pendientes,
                        'el socio sin vincular queda asentado')
        self.assertIn('Persona Inexistente', proposal.socios_pendientes)

    def test_aprobacion_con_nomina_vacia_no_arma_filas_ni_mentira(self):
        """Si la propuesta no trae socios, la nómina queda vacía y el cruce
        dirá que nadie está cubierto: nunca se afirma cobertura sin nombre."""
        proposal = self.env['coop.document.proposal'].create_from_ingestion(
            self._payload_nomina([]))
        proposal.write({'obra_id': self.obra.id})
        proposal.action_approve()
        proposal.invalidate_recordset()
        self.assertEqual(len(proposal.poliza_id.nomina_ids), 0)
