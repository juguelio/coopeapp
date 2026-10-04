"""Local regressions without Odoo; request/ORM are doubles, not HTTP smoke.

Run: .venv/bin/python -m unittest discover -s scripts/tests -v
"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]


def load_controller(name):
    odoo = ModuleType('odoo')
    http = ModuleType('odoo.http')
    http.Controller = object
    http.route = lambda *args, **kw: lambda method: method
    http.request = Mock()
    odoo.http = http
    exceptions = ModuleType('odoo.exceptions')
    exceptions.UserError = type('UserError', (Exception,), {})
    exceptions.ValidationError = type('ValidationError', (Exception,), {})
    spec = importlib.util.spec_from_file_location(
        name, ROOT / 'addons/coop_portal/controllers' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        'odoo': odoo, 'odoo.http': http, 'odoo.exceptions': exceptions,
    }):
        spec.loader.exec_module(module)
    return module


class TestPilotPortal(unittest.TestCase):
    def test_pedir_without_work_renders_explanation_in_same_tab(self):
        module = load_controller('coordinador')
        controller = module.CoopPortalCoordinador()
        member = SimpleNamespace(ids=[7])
        controller._member = Mock(return_value=member)
        module.request.env = {'project.project': Mock()}
        module.request.env['project.project'].sudo().search.return_value = []
        controller.pedir_paso1()
        module.request.redirect.assert_not_called()
        module.request.render.assert_called_once_with(
            'coop_portal.sin_obra', {'member': member, 'nav_activo': 'pedir'})

    def test_pedir_without_member_still_returns_home(self):
        module = load_controller('coordinador')
        controller = module.CoopPortalCoordinador()
        controller._member = Mock(return_value=False)
        controller.pedir_paso1()
        module.request.redirect.assert_called_once_with('/app')
        module.request.render.assert_not_called()

    def test_review_error_keeps_full_message_and_cannot_add_success(self):
        module = load_controller('document_proposal')
        controller = module.CoopPortalDocumentProposal()
        controller._admin = Mock(return_value=True)
        proposal = Mock(id=9)
        reason = 'Revisá A&B + C # pendiente &ok=1'
        proposal.action_approve.side_effect = module.ValidationError(reason)
        model = Mock()
        model.browse.return_value.exists.return_value = proposal
        module.request.env = {'coop.document.proposal': model}
        controller.revision_accion(proposal_id='9', accion='approve')
        location = module.request.redirect.call_args.args[0]
        self.assertEqual(urlsplit(location).path,
                         '/app/admin/revision-documental/9')
        self.assertEqual(parse_qs(urlsplit(location).query), {'error': [reason]})
        self.assertEqual(urlsplit(location).fragment, '')

    def test_no_work_screen_has_large_exit_and_admin_instruction(self):
        tree = ET.parse(ROOT / 'addons/coop_portal/views/portal_templates.xml')
        screen = tree.find(".//template[@id='sin_obra']")
        exits = [a for a in screen.iter('a') if a.get('href') == '/app'
                 and 'botonazo' in a.get('class', '').split()]
        self.assertTrue(exits, 'La pantalla necesita una salida grande al inicio')
        self.assertIn('administrador', ''.join(screen.itertext()).lower())

    def test_help_does_not_promise_other_members_contributions(self):
        tree = ET.parse(ROOT / 'addons/coop_portal/views/portal_templates.xml')
        text = ''.join(tree.getroot().itertext())
        self.assertFalse('todos ven lo que cada uno aportó' in text,
                         'La ayuda promete una vista colectiva que no existe')


if __name__ == '__main__':
    unittest.main()
