from odoo import models, fields


class ProjectTask(models.Model):
    _inherit = 'project.task'

    categoria_tarea = fields.Selection([
        ('excavacion', 'Excavación y movimiento de suelos'),
        ('estructura', 'Estructura'),
        ('albanileria', 'Albañilería'),
        ('electricidad', 'Instalaciones eléctricas'),
        ('sanitaria', 'Instalaciones sanitarias'),
        ('terminaciones', 'Terminaciones'),
        ('otro', 'Otro'),
    ], string='Categoría')
    socio_tarea_ids = fields.Many2many(
        'coop.member', 'task_coop_member_rel', 'task_id', 'member_id',
        string='Cuadrilla asignada', domain=[('state', '=', 'active')])
