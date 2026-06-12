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

    # --- Ruta crítica (CPM) ---
    duracion_dias = fields.Float(
        string='Duración (días)', default=1.0,
        help='Duración estimada de la tarea para el cálculo de ruta crítica')
    inicio_temprano = fields.Float(
        string='Inicio temprano (día)', readonly=True, copy=False,
        help='Día relativo al inicio de obra (calculado por CPM)')
    fin_temprano = fields.Float(
        string='Fin temprano (día)', readonly=True, copy=False)
    holgura = fields.Float(
        string='Holgura (días)', readonly=True, copy=False,
        help='Días que puede atrasarse sin atrasar la obra. 0 = crítica')
    es_critica = fields.Boolean(
        string='Ruta crítica', readonly=True, copy=False,
        help='La tarea está en la hoja de ruta crítica de la obra')
    foja_item_ids = fields.One2many(
        'coop.foja.item', 'task_id', string='Ítems de foja')
