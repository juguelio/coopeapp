"""Contrato de presentación B+A sobre rutas y datos reales de Odoo."""
from lxml import html

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHybridUI(HttpCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Socio UI local'})
        self.user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': self.partner.name, 'login': 'hybrid.ui.test',
            'password': 'Local-UI-Test-Only', 'partner_id': self.partner.id,
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id,
                                 self.env.ref('coop_members.group_coop_member').id])],
        })
        self.member = self.env['coop.member'].with_context(skip_portal_user=True).create({
            'name': self.partner.name, 'partner_id': self.partner.id,
            'dni': '88887101', 'role': 'worker', 'state': 'active',
            'date_admission': '2026-01-01',
        })
        self.obra = self.env['project.project'].create({
            'name': 'Obra UI con nombre largo para probar lectura', 'is_coop_obra': True,
            'socio_obra_ids': [(6, 0, [self.member.id])],
        })
        self.item = self.env['coop.foja.item'].create({
            'obra_id': self.obra.id, 'item': '1', 'name': 'Pared de ladrillo',
            'uom': 'm2', 'cantidad': 100, 'precio_unitario': 12000,
        })

    def page(self, path, mode='cartel'):
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200, path)
        tree = html.fromstring(response.content)
        self.assertIn('ui-' + mode, tree.xpath('//body/@class')[0].split())
        return tree

    def test_worker_pages_and_navigation(self):
        self.authenticate(self.user.login, 'Local-UI-Test-Only')
        for path in ['/app', '/app/aporte', '/app/plata', '/app/ayuda',
                     '/app/cargar', '/app/cargar/otro',
                     '/app/cargar/cantidad?item_id=%d' % self.item.id,
                     '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id]:
            tree = self.page(path)
            self.assertFalse(tree.xpath('//table'), path)
            self.assertEqual(tree.xpath('//div[@class="nav"]/a/@href'),
                             ['/app', '/app/cargar', '/app/pedir', '/app/obra'])
            self.assertNotIn('capataz', tree.text_content().lower())
        for path in ['/app', '/app/aporte', '/app/plata', '/app/ayuda']:
            tree = self.page(path)
            self.assertEqual(len(tree.xpath('//*[contains(concat(" ", @class, " "), " ux-primary ")]')), 1, path)

    def test_no_work_and_confirmation(self):
        self.authenticate(self.user.login, 'Local-UI-Test-Only')
        step = self.page('/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        token = step.xpath('//input[@name="csrf_token"]/@value')[0]
        result = self.url_open('/app/cargar/confirmar', data={
            'csrf_token': token, 'item_id': self.item.id, 'cantidad': '2',
            'medida_trabajo': 'jornal', 'cantidad_trabajo': '1',
        })
        self.assertEqual(result.status_code, 200)
        self.assertIn('Falta que lo valide el coordinador', result.text)
        self.obra.socio_obra_ids = False
        tree = self.page('/app/pedir')
        self.assertIn('Todavía no estás asignado', tree.text_content())
        self.assertTrue(tree.xpath('//a[@href="/app" and contains(@class,"botonazo")]'))

    def test_production_is_not_certified_or_paid(self):
        self.env['coop.avance.medicion'].create({
            'member_id': self.member.id, 'foja_item_id': self.item.id,
            'cantidad': 2, 'cantidad_trabajo': 1, 'medida_trabajo': 'jornal',
        })
        self.env['coop.payroll'].create({
            'member_id': self.member.id, 'date_from': '2026-08-01',
            'date_to': '2026-08-31', 'bonus_amount': 500, 'state': 'review',
        })
        self.authenticate(self.user.login, 'Local-UI-Test-Only')
        aporte = self.page('/app/aporte').text_content()
        self.assertIn('Producción registrada', aporte)
        self.assertNotIn('PRODUCCIÓN CERTIFICADA', aporte)
        self.assertNotIn('el que pone más, cobra más', aporte)
        plata = self.page('/app/plata').text_content()
        self.assertIn('Todavía no está pagada', plata)

    def test_manager_keeps_operational_navigation_and_worker_is_denied(self):
        self.authenticate(self.user.login, 'Local-UI-Test-Only')
        self.assertTrue(self.url_open('/app/admin').url.endswith('/app'))
        self.member.role = 'manager'
        tree = self.page('/app/admin', mode='obra')
        self.assertEqual(tree.xpath('//div[@class="nav"]/a/@href'), [
            '/app/admin', '/app/admin/ruta', '/app/admin/reportes',
            '/app/admin/revision-documental', '/app/asamblea'])
