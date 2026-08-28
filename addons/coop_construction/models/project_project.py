import math
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


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
    nivel_riesgo = fields.Selection([
        ('bajo', 'Bajo'),
        ('medio', 'Medio'),
        ('alto', 'Alto'),
    ], string='Nivel de riesgo', default='medio', tracking=True,
        help='En obras de alto riesgo no se puede asignar plantel sin cobertura '
             'vigente y paga o una excepción registrada vigente. En bajo y '
             'medio solo hay aviso, como hasta ahora.')
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

    # ── Contrato: fechas y atraso contra la ruta crítica ─────────────
    contrato_ids = fields.One2many(
        'coop.contrato', 'obra_id', string='Contratos')
    fecha_inicio_contractual = fields.Date(
        string='Inicio contractual', compute='_compute_fechas_contractuales',
        store=True,
        help='Del contrato más reciente. La obra sin contrato no tiene fecha '
             'y no muestra atraso.')
    fecha_fin_contractual = fields.Date(
        string='Fin contractual', compute='_compute_fechas_contractuales',
        store=True)
    duracion_cpm_dias = fields.Float(
        string='Duración por ruta crítica (días)', readonly=True, copy=False,
        help='Días totales del último cálculo de ruta crítica. Se escribe al '
             'apretar "Calcular ruta crítica".')
    fin_obra_estimado = fields.Date(
        string='Fin estimado (ruta crítica)',
        compute='_compute_atraso_contrato', store=True,
        help='Inicio contractual + duración de la ruta crítica.')
    atraso_dias = fields.Integer(
        string='Atraso contra contrato (días)',
        compute='_compute_atraso_contrato', store=True,
        help='Positivo = la obra termina tarde contra el fin contractual. '
             'Negativo = adelanto. Requiere contrato y ruta crítica calculada.')

    @api.depends('contrato_ids.fecha_inicio', 'contrato_ids.fecha_fin')
    def _compute_fechas_contractuales(self) -> None:
        for obra in self:
            vigente = obra.contrato_ids[:1]  # _order: fecha_inicio desc, id desc
            obra.fecha_inicio_contractual = vigente.fecha_inicio or False
            obra.fecha_fin_contractual = vigente.fecha_fin or False

    @api.depends('duracion_cpm_dias', 'fecha_inicio_contractual',
                 'fecha_fin_contractual')
    def _compute_atraso_contrato(self) -> None:
        for obra in self:
            if (obra.duracion_cpm_dias and obra.fecha_inicio_contractual
                    and obra.fecha_fin_contractual):
                fin_est = obra.fecha_inicio_contractual + timedelta(
                    days=math.ceil(obra.duracion_cpm_dias))
                obra.fin_obra_estimado = fin_est
                obra.atraso_dias = (fin_est - obra.fecha_fin_contractual).days
            else:
                obra.fin_obra_estimado = False
                obra.atraso_dias = 0

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

    @api.constrains('socio_obra_ids', 'nivel_riesgo')
    def _check_cobertura_alto_riesgo(self) -> None:
        """En obra de alto riesgo, asignar plantel sin cobertura es un bloqueo
        duro. Germán (28/08): "hay lugares que sin la nomina en mano no te
        dejan entrar". La escapatoria sigue siendo la excepción registrada
        (quién asume el riesgo y hasta cuándo): `socios_sin_cobertura` ya la
        descuenta. En bajo y medio no se toca nada: sigue el aviso no
        bloqueante de `_onchange_aviso_cobertura`."""
        for obra in self:
            if not obra.is_coop_obra or obra.nivel_riesgo != 'alto':
                continue
            sin = obra.socios_sin_cobertura()
            if sin:
                raise ValidationError(_(
                    'Obra de alto riesgo: no se puede asignar a %s sin una '
                    'póliza vigente y paga que los cubra. Si igual tienen que '
                    'arrancar, registrá una excepción (quién asume el riesgo y '
                    'hasta cuándo) en la pestaña Seguros de la obra.'
                ) % ', '.join(sin.mapped('name')))

    def action_calcular_ruta_critica(self) -> None:
        """Calcula la ruta crítica (CPM) sobre las tareas de la obra.

        Usa las dependencias entre tareas (depend_on_ids) y duracion_dias.
        Marca es_critica, holgura, inicio y fin temprano de cada tarea.
        """
        self.ensure_one()
        # OJO: `task_ids` excluye las tareas cerradas. Si se usa acá, marcar una
        # tarea como terminada la saca del cálculo y el plan se comprime como si
        # esos días nunca se hubieran trabajado (las que venían después pasan a
        # arrancar el día 0). La ruta se calcula sobre TODAS las tareas.
        tasks = self.env['project.task'].search([('project_id', '=', self.id)])
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
        # Se persiste para que el atraso contra el contrato (una resta sobre
        # esta duración) se recalcule sin volver a correr el CPM entero.
        self.duracion_cpm_dias = fin_obra

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
                # Una tarea terminada ya no puede atrasar la obra, así que sale
                # del camino crítico aunque su holgura siga siendo cero. La
                # duración NO se toca: esos días se consumieron de verdad y las
                # tareas que venían después no arrancan antes por cerrarla.
                'es_critica': abs(holgura) < 0.01 and not task.esta_terminada,
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
