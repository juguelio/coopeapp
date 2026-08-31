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
