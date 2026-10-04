"""Remove management grants inherited by the former syndic hierarchy."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    syndic = env.ref('coop_members.group_coop_syndic')
    management = env['res.groups']
    for xmlid in ('coop_members.group_coop_manager',
                  'coop_members.group_coop_coordinador',
                  'project.group_project_manager',
                  'project.group_project_user'):
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            management |= group
    users = env['res.users'].with_context(active_test=False).search([
        ('groups_id', 'in', syndic.ids),
    ])
    users.write({'groups_id': [(3, group.id) for group in management]})
