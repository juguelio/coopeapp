from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def create(self, vals_list):
        users = super().create(vals_list)
        action = self.env.ref(
            'coop_members.action_coop_member', raise_if_not_found=False,
        )
        if action:
            users.filtered(lambda u: not u.action_id).write(
                {'action_id': action.id}
            )
        return users
