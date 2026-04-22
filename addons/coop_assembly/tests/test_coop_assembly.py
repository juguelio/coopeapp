from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from datetime import datetime


@tagged('post_install', '-at_install')
class TestCoopAssembly(TransactionCase):

    def setUp(self):
        super().setUp()
        # Crear socios activos
        for i in range(5):
            partner = self.env['res.partner'].create({'name': f'Socio {i}'})
            self.env['coop.member'].create({
                'name': f'Socio {i}',
                'partner_id': partner.id,
                'dni': f'1234567{i}',
                'role': 'worker',
                'state': 'active',
                'date_admission': '2024-01-01',
            })

        self.members = self.env['coop.member'].search([('state', '=', 'active')])

        self.assembly = self.env['coop.assembly'].create({
            'name': 'Asamblea Ordinaria Abril 2026',
            'assembly_type': 'ordinary',
            'date': datetime(2026, 4, 21, 18, 0),
            'location': 'Sede de la cooperativa',
            'quorum_required': 50,
        })

    def test_assembly_creation(self):
        self.assertEqual(self.assembly.state, 'draft')
        self.assertFalse(self.assembly.quorum_reached)

    def test_quorum_calculation(self):
        self.assembly.attendee_ids = [(6, 0, self.members[:4].ids)]
        self.assembly._compute_quorum()
        self.assertTrue(self.assembly.quorum_reached)

    def test_cannot_open_without_quorum(self):
        self.assembly.attendee_ids = [(6, 0, self.members[:1].ids)]
        with self.assertRaises(ValidationError):
            self.assembly.action_open()

    def test_vote_simple_majority(self):
        vote = self.env['coop.vote'].create({
            'name': 'Aprobar presupuesto anual',
            'assembly_id': self.assembly.id,
            'vote_type': 'simple',
            'votes_yes': 3,
            'votes_no': 2,
            'votes_abstain': 0,
        })
        self.assertTrue(vote.approved)

    def test_vote_absolute_majority(self):
        vote = self.env['coop.vote'].create({
            'name': 'Modificación de estatuto',
            'assembly_id': self.assembly.id,
            'vote_type': 'absolute',
            'votes_yes': 3,
            'votes_no': 3,
            'votes_abstain': 0,
        })
        self.assertFalse(vote.approved)

    def test_vote_unanimous(self):
        vote = self.env['coop.vote'].create({
            'name': 'Disolución de la cooperativa',
            'assembly_id': self.assembly.id,
            'vote_type': 'unanimous',
            'votes_yes': 5,
            'votes_no': 0,
            'votes_abstain': 0,
        })
        self.assertTrue(vote.approved)

    def test_generate_minutes(self):
        self.assembly.attendee_ids = [(6, 0, self.members.ids)]
        self.assembly.action_open()
        self.env['coop.vote'].create({
            'name': 'Test votación',
            'assembly_id': self.assembly.id,
            'vote_type': 'simple',
            'votes_yes': 4,
            'votes_no': 1,
            'state': 'closed',
        })
        self.assembly.action_generate_minutes()
        self.assertTrue(self.assembly.minutes)
        self.assertIn('Asamblea Ordinaria Abril 2026', self.assembly.minutes)
