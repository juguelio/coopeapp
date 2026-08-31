from datetime import date

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestDocumentProposalPortal(HttpCase):
    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({
            'name': 'Sofía Test Portal',
            'email': 'sofia.portal@coopeapp.demo',
        })
        manager_group = self.env.ref('coop_members.group_coop_manager')
        self.user = self.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Sofía Test Portal',
            'login': 'sofia.portal.test',
            'password': 'DemoOnly-Portal-2026',
            'partner_id': partner.id,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                manager_group.id,
            ])],
        })
        self.env['coop.member'].with_context(
            skip_portal_user=True,
        ).create({
            'name': 'Sofía Test Portal',
            'partner_id': partner.id,
            'dni': '99999991',
            'role': 'manager',
            'state': 'active',
            'date_admission': date(2026, 1, 1),
        })
        self.proposal = self.env['coop.document.proposal'].create({
            'source_file_name': 'POLIZA-DEMO-QUINTRIQUEO.pdf',
            'box_file_id': '2438121470111',
            'box_version_id': '2703223890911',
            'source_sha256': 'demo-sha256',
            'numero': 'DEMO-2026-001',
            'aseguradora': 'Patagonia Seguros Demo',
            'obra_nombre_extraido': 'Quintriqueo',
            'fecha_inicio': '2026-09-01',
            'fecha_fin': '2027-08-31',
            'importe': 185000.0,
            'socios_extraidos': 'Diego López\nMaría González\nPablo Castillo',
            'state': 'pending_review',
        })

    def test_admin_sees_document_queue_and_actions(self):
        self.authenticate(self.user.login, 'DemoOnly-Portal-2026')
        response = self.url_open('/app/admin/revision-documental')
        body = response.text
        self.assertEqual(response.status_code, 200)
        self.assertIn('Revisión documental', body)
        self.assertIn('POLIZA-DEMO-QUINTRIQUEO.pdf', body)
        self.assertIn('Pendiente de revisión', body)

        detail = self.url_open('/app/admin/revision-documental/%d' % self.proposal.id)
        detail_body = detail.text
        self.assertEqual(detail.status_code, 200)
        self.assertIn('APROBAR PROPUESTA', detail_body)
        self.assertIn('Obra que corresponde', detail_body)
        self.assertIn('PEDIR CORRECCIÓN', detail_body)
        self.assertIn('RECHAZAR', detail_body)
        self.assertIn('2438121470111', detail_body)
        self.assertIn('2703223890911', detail_body)
