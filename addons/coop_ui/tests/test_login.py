from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestBackendLoginFallback(HttpCase):
    def test_backend_login_form_is_visible_without_user_switch(self):
        response = self.url_open('/web/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="oe_login_form"', response.text)
        self.assertNotIn('oe_login_form d-none', response.text)
        self.assertIn('name="login"', response.text)
        self.assertIn('name="password"', response.text)
        self.assertIn('type="submit"', response.text)
