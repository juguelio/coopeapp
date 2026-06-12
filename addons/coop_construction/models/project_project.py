from odoo import models, fields, api
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_coop_obra = fields.Boolean(string='Es obra cooperativa', default=False)
    obra_type = fields.Selection([
        ('vivienda', 'Vivienda'),
        ('infraestructura', 'Infraestructura'),
        ('industrial', 'Industrial'),
        ('vial', 'Vial'),
        ('otro', 'Otro'),
    ], string='Tipo de obra')
    comitente_id = fields.Many2one(
        'res.partner', string='Comitente', ondelete='restrict')
    numero_expediente = fields.Char(string='N° expediente / contrato')
    monto_contrato = fields.Monetary(string='Monto del contrato')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)
    ubicacion = fields.Char(string='Ubicación de la obra')
    director_id = fields.Many2one(
        'coop.member', string='Director de obra', ondelete='restrict',
        domain=[('state', '=', 'active')])
    capataz_id = fields.Many2one(
        'coop.member', string='Capataz principal', ondelete='restrict',
        domain=[('state', '=', 'active')])
    socio_obra_ids = fields.Many2many(
        'coop.member', 'project_coop_member_rel', 'project_id', 'member_id',
        string='Plantel asignado', domain=[('state', '=', 'active')])
    estado_obra = fields.Selection([
        ('planificacion', 'Planificación'),
        ('activa', 'Activa'),
        ('suspendida', 'Suspendida'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ], string='Estado de obra', default='planificacion', tracking=True)
    hour_rate = fields.Monetary(
        string='Tarifa horaria (obra)', currency_field='currency_id',
        help='Tarifa por hora negociada con el comitente para esta obra')
    obra_work_entry_ids = fields.One2many(
        'coop.work.entry', 'obra_id', string='Entradas de trabajo de obra')
    costo_mano_obra = fields.Monetary(
        string='Costo mano de obra', compute='_compute_costo_mano_obra',
        currency_field='currency_id', store=True)
    certificado_ids = fields.One2many(
        'coop.certificado', 'obra_id', string='Certificados')
    etapa_ids = fields.One2many(
        'coop.etapa', 'obra_id', string='Etapas')
    etapa_count = fields.Integer(
        string='Etapas', compute='_compute_etapa_count')
    foja_item_ids = fields.One2many(
        'coop.foja.item', 'obra_id', string='Foja de medición')
    avance_fisico = fields.Float(
        string='Avance físico (%)', compute='_compute_avance_fisico',
        store=True, digits=(5, 2),
        help='Suma del avance de cada ítem ponderado por su incidencia')
    certificado_count = fields.Integer(
        string='Certificados', compute='_compute_certificado_count')
    total_certificado = fields.Monetary(
        string='Total certificado', compute='_compute_total_certificado',
        currency_field='currency_id', store=True)

    @api.depends('obra_work_entry_ids.hours', 'hour_rate')
    def _compute_costo_mano_obra(self) -> None:
        for record in self:
            total_hours = sum(record.obra_work_entry_ids.mapped('hours'))
            record.costo_mano_obra = total_hours * (record.hour_rate or 0.0)

    @api.depends('certificado_ids')
    def _compute_certificado_count(self) -> None:
        for record in self:
            record.certificado_count = len(record.certificado_ids)

    @api.depends('certificado_ids.monto_certificado', 'certificado_ids.state')
    def _compute_total_certificado(self) -> None:
        for record in self:
            cobrados = record.certificado_ids.filtered(
                lambda c: c.state in ('aprobado', 'cobrado'))
            record.total_certificado = sum(cobrados.mapped('monto_certificado'))

    @api.depends('etapa_ids')
    def _compute_etapa_count(self) -> None:
        for record in self:
            record.etapa_count = len(record.etapa_ids)

    @api.depends('foja_item_ids.aporte_pct')
    def _compute_avance_fisico(self) -> None:
        for record in self:
            record.avance_fisico = sum(
                record.foja_item_ids.mapped('aporte_pct'))

    def action_calcular_ruta_critica(self) -> None:
        """Calcula la ruta crítica (CPM) sobre las tareas de la obra.

        Usa las dependencias entre tareas (depend_on_ids) y duracion_dias.
        Marca es_critica, holgura, inicio y fin temprano de cada tarea.
        """
        self.ensure_one()
        tasks = self.task_ids
        if not tasks:
            raise UserError('La obra no tiene tareas para calcular.')

        # Forward pass (orden topológico)
        early = {}  # task.id -> (inicio_temprano, fin_temprano)
        pending = set(tasks.ids)
        while pending:
            progress = False
            for task in tasks:
                if task.id not in pending:
                    continue
                deps = task.depend_on_ids.filtered(lambda t: t.id in tasks.ids)
                if any(d.id in pending for d in deps):
                    continue
                start = max(
                    (early[d.id][1] for d in deps), default=0.0)
                early[task.id] = (start, start + (task.duracion_dias or 0.0))
                pending.discard(task.id)
                progress = True
            if not progress:
                raise UserError(
                    'Hay dependencias circulares entre las tareas: '
                    'revisá las tareas bloqueadas entre sí.')

        fin_obra = max(ef for _, ef in early.values())

        # Backward pass
        late_finish = {}
        for task in tasks:
            successors = tasks.filtered(lambda t: task in t.depend_on_ids)
            late_finish[task.id] = None if successors else fin_obra
        pending = {tid for tid, lf in late_finish.items() if lf is None}
        while pending:
            progress = False
            for task in tasks:
                if task.id not in pending:
                    continue
                successors = tasks.filtered(lambda t: task in t.depend_on_ids)
                if any(s.id in pending for s in successors):
                    continue
                late_finish[task.id] = min(
                    late_finish[s.id] - (s.duracion_dias or 0.0)
                    for s in successors)
                pending.discard(task.id)
                progress = True
            if not progress:
                break

        for task in tasks:
            es, ef = early[task.id]
            holgura = late_finish[task.id] - ef
            task.write({
                'inicio_temprano': es,
                'fin_temprano': ef,
                'holgura': holgura,
                'es_critica': abs(holgura) < 0.01,
            })

    def action_open_etapas(self) -> dict:
        return {
            'type': 'ir.actions.act_window',
            'name': 'Proyección por Etapas',
            'res_model': 'coop.etapa',
            'view_mode': 'list,form',
            'domain': [('obra_id', '=', self.id)],
            'context': {'default_obra_id': self.id},
        }

    def action_open_certificados(self) -> dict:
        return {
            'type': 'ir.actions.act_window',
            'name': 'Certificados',
            'res_model': 'coop.certificado',
            'view_mode': 'list,form',
            'domain': [('obra_id', '=', self.id)],
            'context': {'default_obra_id': self.id},
        }
