"""Contrato de pertenencia a la obra en el portal.

Las record rules del avance y del pedido dejan crear el registro propio y **no
miran la obra** (`rule_avance_medicion_member_write`, `rule_pedido_member_write`):
el control tiene que estar en el controller. Estos tests fijan ese contrato con
un socio que intenta cargar trabajo y pedir materiales contra la foja / la obra
de otro, escribiendo el id a mano (el mismo id que un teléfono puede mandar en
la cola offline).
"""
import json

from lxml import html

from odoo.tests import HttpCase, tagged

PASSWORD = 'Local-Pertenencia-Test'


@tagged('post_install', '-at_install')
class TestObraPertenencia(HttpCase):

    def setUp(self):
        super().setUp()
        self.socio = self._socio('Socio A', 'pertenencia.a', '77777001')
        self.ajeno = self._socio('Socio B', 'pertenencia.b', '77777002')
        self.obra = self.env['project.project'].create({
            'name': 'Obra del socio A', 'is_coop_obra': True,
            'socio_obra_ids': [(6, 0, [self.socio.id])],
        })
        self.obra_ajena = self.env['project.project'].create({
            'name': 'Obra del socio B', 'is_coop_obra': True,
            'socio_obra_ids': [(6, 0, [self.ajeno.id])],
        })
        self.item = self.env['coop.foja.item'].create({
            'obra_id': self.obra.id, 'item': '1', 'name': 'Pared propia',
            'uom': 'm2', 'cantidad': 100, 'precio_unitario': 10000,
        })
        self.item_ajeno = self.env['coop.foja.item'].create({
            'obra_id': self.obra_ajena.id, 'item': '1', 'name': 'Pared ajena',
            'uom': 'm2', 'cantidad': 100, 'precio_unitario': 10000,
        })

    # ── helpers ──────────────────────────────────────────────────────
    def _socio(self, name, login, dni):
        partner = self.env['res.partner'].create({'name': name})
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': name, 'login': login, 'password': PASSWORD,
            'partner_id': partner.id,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('coop_members.group_coop_member').id])],
        })
        return self.env['coop.member'].with_context(
            skip_portal_user=True).create({
                'name': name, 'partner_id': partner.id, 'dni': dni,
                'role': 'worker', 'state': 'active',
                'date_admission': '2026-01-01',
            })

    def _token(self, path):
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200, path)
        return html.fromstring(response.content).xpath(
            '//input[@name="csrf_token"]/@value')[0]

    def _avances(self, member):
        return self.env['coop.avance.medicion'].search_count(
            [('member_id', '=', member.id)])

    def _pedidos(self, member):
        return self.env['coop.pedido.material'].search_count(
            [('member_id', '=', member.id)])

    # ── cargar avance ────────────────────────────────────────────────
    def test_cargar_avance_solo_contra_la_foja_propia(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        ajeno = self.url_open('/app/cargar/confirmar', data={
            'csrf_token': token, 'item_id': self.item_ajeno.id, 'cantidad': '2',
            'medida_trabajo': 'jornal', 'cantidad_trabajo': '1'})
        self.assertTrue(ajeno.url.endswith('/app/cargar'), ajeno.url)
        self.assertEqual(self._avances(self.socio), 0)
        self.assertEqual(self._avances(self.ajeno), 0)
        # control: lo propio sí entra (la guarda no bloquea el camino real)
        propio = self.url_open('/app/cargar/confirmar', data={
            'csrf_token': token, 'item_id': self.item.id, 'cantidad': '2',
            'medida_trabajo': 'jornal', 'cantidad_trabajo': '1'})
        self.assertIn('Falta que lo valide el coordinador', propio.text)
        self.assertEqual(self._avances(self.socio), 1)

    def test_el_wizard_no_muestra_la_foja_ajena(self):
        self.authenticate('pertenencia.a', PASSWORD)
        for path in ['/app/cargar/cantidad?item_id=%d' % self.item_ajeno.id,
                     '/app/cargar/trabajo?item_id=%d&cantidad=2'
                     % self.item_ajeno.id]:
            respuesta = self.url_open(path)
            self.assertTrue(respuesta.url.endswith('/app/cargar'), path)
            self.assertNotIn('Pared ajena', respuesta.text)
        propio = self.url_open('/app/cargar/cantidad?item_id=%d' % self.item.id)
        self.assertEqual(propio.status_code, 200)
        self.assertIn('Pared propia', propio.text)

    def test_sync_offline_rechaza_el_item_ajeno(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        ajeno = self.url_open('/app/cargar/sync', data={
            'csrf_token': token, 'item_id': self.item_ajeno.id, 'cantidad': '2',
            'medida_trabajo': 'jornal', 'cantidad_trabajo': '1'})
        self.assertFalse(json.loads(ajeno.text)['ok'])
        self.assertEqual(self._avances(self.socio), 0)
        propio = self.url_open('/app/cargar/sync', data={
            'csrf_token': token, 'item_id': self.item.id, 'cantidad': '2',
            'medida_trabajo': 'jornal', 'cantidad_trabajo': '1'})
        self.assertTrue(json.loads(propio.text)['ok'])
        self.assertEqual(self._avances(self.socio), 1)

    # ── pedir materiales ─────────────────────────────────────────────
    def test_pedido_solo_en_la_obra_propia(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/pedir/cantidad?obra_id=%d&material_id=otro' % self.obra.id)
        datos = {'csrf_token': token, 'material_id': 'otro',
                 'descripcion': 'Membrana asfáltica', 'cantidad': '3',
                 'uom': 'unidad'}
        ajeno = self.url_open(
            '/app/pedir/confirmar', data=dict(datos, obra_id=self.obra_ajena.id))
        self.assertTrue(ajeno.url.endswith('/app/pedir'), ajeno.url)
        self.assertEqual(self._pedidos(self.socio), 0)
        propio = self.url_open(
            '/app/pedir/confirmar', data=dict(datos, obra_id=self.obra.id))
        self.assertEqual(propio.status_code, 200)
        self.assertEqual(self._pedidos(self.socio), 1)

    def test_el_paso_de_cantidad_no_abre_la_obra_ajena(self):
        self.authenticate('pertenencia.a', PASSWORD)
        respuesta = self.url_open(
            '/app/pedir/cantidad?obra_id=%d&material_id=otro' % self.obra_ajena.id)
        self.assertTrue(respuesta.url.endswith('/app/pedir'), respuesta.url)

    # ── ids rotos: rebote, no 500 ────────────────────────────────────
    def test_id_no_numerico_rebota_en_vez_de_romper(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        cargar = self.url_open('/app/cargar/confirmar', data={
            'csrf_token': token, 'item_id': 'abc', 'cantidad': '2',
            'medida_trabajo': 'jornal', 'cantidad_trabajo': '1'})
        self.assertTrue(cargar.url.endswith('/app/cargar'), cargar.url)
        paso2 = self.url_open('/app/cargar/cantidad?item_id=abc')
        self.assertTrue(paso2.url.endswith('/app/cargar'), paso2.url)
        pedir = self.url_open('/app/pedir/confirmar', data={
            'csrf_token': token, 'obra_id': 'abc', 'material_id': 'otro',
            'descripcion': 'Membrana', 'cantidad': '3', 'uom': 'unidad'})
        self.assertTrue(pedir.url.endswith('/app/pedir'), pedir.url)
        self.assertEqual(self._avances(self.socio), 0)
        self.assertEqual(self._pedidos(self.socio), 0)

    def test_otro_no_reasigna_una_obra_invalida(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token('/app/cargar/otro?obra_id=%d' % self.obra.id)
        for obra_id in (str(self.obra_ajena.id), 'abc', ''):
            response = self.url_open('/app/cargar/otro/confirmar', data={
                'csrf_token': token, 'obra_id': obra_id,
                'descripcion': 'Limpieza', 'medida_trabajo': 'hora',
                'cantidad_trabajo': '2'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.url.endswith('/app/cargar'), response.url)
        self.assertFalse(self.env['coop.trabajo.otro'].search_count([
            ('member_id', '=', self.socio.id)]))

    def test_cantidades_no_finitas_no_crean_registros(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        for cantidad in ('nan', 'inf', '-inf', '1e309'):
            for field in ('cantidad', 'cantidad_trabajo'):
                data = {'csrf_token': token, 'item_id': self.item.id,
                        'cantidad': '2', 'medida_trabajo': 'hora',
                        'cantidad_trabajo': '1'}
                data[field] = cantidad
                response = self.url_open('/app/cargar/confirmar', data=data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.url.endswith('/app/cargar'), response.url)
                response = self.url_open('/app/cargar/sync', data=data)
                self.assertFalse(json.loads(response.text)['ok'])
            response = self.url_open('/app/pedir/confirmar', data={
                'csrf_token': token, 'obra_id': self.obra.id,
                'material_id': 'otro', 'descripcion': 'Membrana',
                'cantidad': cantidad, 'uom': 'unidad'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.url.endswith('/app/pedir'), response.url)
        self.assertEqual(self._avances(self.socio), 0)
        self.assertEqual(self._pedidos(self.socio), 0)

    def test_sync_no_atribuye_cola_de_otro_usuario(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        response = self.url_open('/app/cargar/sync', data={
            'csrf_token': token, 'item_id': self.item.id, 'cantidad': '2',
            'medida_trabajo': 'hora', 'cantidad_trabajo': '1',
            'queue_uid': self.ajeno.partner_id.user_ids[:1].id})
        self.assertFalse(json.loads(response.text)['ok'])
        self.assertEqual(self._avances(self.socio), 0)

    def test_sync_reintento_no_duplica_la_carga(self):
        self.authenticate('pertenencia.a', PASSWORD)
        token = self._token(
            '/app/cargar/trabajo?item_id=%d&cantidad=2' % self.item.id)
        datos = {'csrf_token': token, 'item_id': self.item.id, 'cantidad': '2',
                 'medida_trabajo': 'hora', 'cantidad_trabajo': '1',
                 'sync_token': 'abc12300' * 4}
        for intento in range(2):
            response = self.url_open('/app/cargar/sync', data=datos)
            self.assertTrue(json.loads(response.text)['ok'])
        self.assertEqual(self._avances(self.socio), 1)
        avance = self.env['coop.avance.medicion'].search([
            ('member_id', '=', self.socio.id)])
        avance.action_validar()
        response = self.url_open('/app/cargar/sync', data=datos)
        self.assertTrue(json.loads(response.text)['ok'])
        self.assertEqual(self._avances(self.socio), 1)

    def test_sindico_sin_grupo_manager_puede_firmar_en_portal(self):
        self.socio.write({'role': 'syndic'})
        user = self.socio.partner_id.user_ids[:1]
        user.write({'groups_id': [(6, 0, [
            self.env.ref('base.group_user').id,
            self.env.ref('coop_members.group_coop_syndic').id])]})
        self.assertFalse(user.has_group('coop_members.group_coop_manager'))
        cert = self.env['coop.certificado'].create({
            'name': 'Certificado para fiscalizar', 'obra_id': self.obra.id,
            'numero': 1, 'monto_certificado': 10000, 'state': 'presentado'})
        self.authenticate('pertenencia.a', PASSWORD)
        for path in ('/app/control', '/app/certificados', '/app/auditoria'):
            self.assertEqual(self.url_open(path).status_code, 200, path)
        token = self._token('/app/firmar?cert_id=%d' % cert.id)
        response = self.url_open('/app/firmar/confirmar', data={
            'csrf_token': token, 'cert_id': cert.id})
        self.assertEqual(response.status_code, 200)
        cert.invalidate_recordset()
        self.assertTrue(cert.firmado)
        self.assertEqual(cert.firmado_por_id, self.socio)
