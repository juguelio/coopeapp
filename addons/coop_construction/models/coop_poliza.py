"""Seguros: habilitación para trabajar, no archivo de PDFs.

La cooperativa no tiene ART —los asociados no están en relación de
dependencia— así que la cobertura depende de pólizas que hay que mantener
vigentes persona por persona, mientras la gente rota entre obras. Hoy eso vive
en una planilla y en la memoria de Yamila.

La pregunta que este módulo tiene que contestar es una sola:

    ¿esta persona puede trabajar en esta obra hoy?

Tres cosas que están en el modelo desde el día uno porque después no se
arreglan sin migración:

1. **Vigente ≠ pago.** Una póliza dentro de plazo pero con la cuota impaga NO
   cubre, y es el caso peligroso: el que un solo campo `state` esconde. Por eso
   el pago vive en las cuotas y la cobertura se calcula de los dos ejes.

2. **La app nunca infiere "pago" de la ausencia de información.** Si nadie
   cargó el comprobante, el estado es *sin confirmar*, no *pago*. Que la app
   diga "cubierto" cuando no lo está es peor que no tener app: reemplaza una
   preocupación real por una tranquilidad falsa. Ante la duda dice *no sé*.

3. **La nómina es una línea por persona y período, no un many2many.** Lo que
   hay que poder contestar el día del accidente es "¿estaba en la nómina en esa
   fecha?", y un many2many solo sabe el estado de hoy.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# Los tres sujetos asegurados. No es un `tipo` con quince opciones y reglas
# escondidas: persona, obra y bien tienen cardinalidades distintas y mezclarlos
# es la forma segura de que dentro de seis meses nadie entienda por qué una
# alerta no salta.
SUJETO = [
    ('persona', 'Personas (nómina)'),
    ('obra', 'Una obra o contratación'),
    ('bien', 'Un bien (vehículo, maquinaria)'),
]

TIPO_POLIZA = [
    ('general', 'General nominal'),
    ('caucion', 'Caución'),
    ('terceros', 'Responsabilidad civil contra terceros'),
    ('altura', 'Trabajo en altura'),
    ('vehiculo', 'Vehículo'),
    ('personal', 'Accidentes personales del socio'),
    ('arca', 'ARCA / situación fiscal'),
    ('otro', 'Otro'),
]


class CoopPoliza(models.Model):
    _name = 'coop.poliza'
    _description = 'Póliza de seguro'
    _order = 'fecha_fin desc, id desc'

    name = fields.Char(string='Póliza', compute='_compute_name', store=True)
    numero = fields.Char(string='Número de póliza', required=True)
    aseguradora_id = fields.Many2one('res.partner', string='Aseguradora')
    sujeto = fields.Selection(
        SUJETO, string='Qué asegura', required=True, default='persona')
    tipo = fields.Selection(TIPO_POLIZA, string='Tipo', required=True)
    # Texto libre a propósito: estructurar la cobertura antes de tener diez
    # pólizas reales adelante es inventar un esquema sobre nada.
    cobertura = fields.Text(string='Qué cubre y hasta cuánto')

    fecha_inicio = fields.Date(string='Vigente desde', required=True)
    fecha_fin = fields.Date(string='Vigente hasta', required=True)

    documento = fields.Many2one(
        'ir.attachment', string='PDF de la póliza',
        help='Respaldo. NO es el dato: lo que la app usa son las fechas y la '
             'nómina.')

    obra_id = fields.Many2one(
        'project.project', string='Obra', domain=[('is_coop_obra', '=', True)],
        help='Solo para pólizas de obra o contratación.')
    equipment_id = fields.Many2one(
        'maintenance.equipment', string='Bien asegurado',
        help='Solo para vehículos y maquinaria.')
    member_id = fields.Many2one(
        'coop.member', string='Socio',
        help='Solo para las personales del socio.')

    nomina_ids = fields.One2many('coop.poliza.nomina', 'poliza_id',
                                 string='Nómina')
    cuota_ids = fields.One2many('coop.poliza.cuota', 'poliza_id',
                                string='Cuotas')

    vigente = fields.Boolean(string='Dentro de vigencia',
                             compute='_compute_cobertura', search='_search_vigente')
    estado_pago = fields.Selection([
        ('al_dia', 'Al día'),
        ('sin_confirmar', 'Sin confirmar'),
        ('vencido', 'Cuota vencida'),
        ('sin_cuotas', 'Sin cuotas cargadas'),
    ], string='Pago', compute='_compute_cobertura')
    cubre = fields.Selection([
        ('si', 'Cubre'),
        ('no', 'NO cubre'),
        ('no_se', 'No sabemos'),
    ], string='¿Cubre hoy?', compute='_compute_cobertura',
        help='"No sabemos" no es un estado intermedio simpático: es lo que la '
             'app tiene que decir cuando le falta información, en vez de '
             'afirmar una cobertura que no puede probar.')
    motivo_cobertura = fields.Char(
        string='Por qué', compute='_compute_cobertura',
        help='De dónde sale el estado de arriba. Una afirmación de cobertura '
             'sin derivación visible es un checkbox con otro nombre.')

    dias_para_vencer = fields.Integer(
        string='Días para vencer', compute='_compute_cobertura')

    _sql_constraints = [
        ('vigencia_coherente', 'CHECK(fecha_fin >= fecha_inicio)',
         'La póliza no puede terminar antes de empezar.'),
    ]

    @api.depends('numero', 'tipo')
    def _compute_name(self) -> None:
        etiquetas = dict(TIPO_POLIZA)
        for p in self:
            p.name = '%s — %s' % (etiquetas.get(p.tipo, p.tipo or ''),
                                  p.numero or 's/n')

    @api.constrains('sujeto', 'obra_id', 'equipment_id', 'member_id')
    def _check_sujeto(self) -> None:
        """Cada sujeto necesita lo suyo. Una póliza de obra sin obra no se
        puede cruzar con nada, y una de bien sin bien tampoco."""
        for p in self:
            if p.sujeto == 'obra' and not p.obra_id:
                raise ValidationError(_(
                    'Una póliza de obra necesita decir de qué obra es.'))
            if p.sujeto == 'bien' and not p.equipment_id:
                raise ValidationError(_(
                    'Una póliza de un bien necesita decir qué bien asegura.'))

    @api.depends('fecha_inicio', 'fecha_fin',
                 'cuota_ids.estado', 'cuota_ids.vencimiento')
    def _compute_cobertura(self) -> None:
        hoy = fields.Date.context_today(self)
        for p in self:
            p.vigente = bool(
                p.fecha_inicio and p.fecha_fin
                and p.fecha_inicio <= hoy <= p.fecha_fin)
            p.dias_para_vencer = (p.fecha_fin - hoy).days if p.fecha_fin else 0

            cuotas = p.cuota_ids
            if not cuotas:
                p.estado_pago = 'sin_cuotas'
            elif any(c.estado == 'vencido' for c in cuotas):
                p.estado_pago = 'vencido'
            elif any(c.estado == 'sin_confirmar' and c.vencimiento
                     and c.vencimiento <= hoy for c in cuotas):
                p.estado_pago = 'sin_confirmar'
            else:
                p.estado_pago = 'al_dia'

            # El cruce de los dos ejes. El orden importa: primero lo que se
            # sabe con certeza (fuera de vigencia, cuota vencida), y recién
            # después lo que no se sabe.
            if not p.vigente:
                p.cubre = 'no'
                p.motivo_cobertura = _('Fuera de vigencia (venció el %s).') % p.fecha_fin
            elif p.estado_pago == 'vencido':
                p.cubre = 'no'
                p.motivo_cobertura = _(
                    'Dentro de vigencia pero con una cuota VENCIDA. Una '
                    'póliza impaga no cubre.')
            elif p.estado_pago == 'sin_confirmar':
                p.cubre = 'no_se'
                p.motivo_cobertura = _(
                    'Dentro de vigencia, pero hay una cuota vencida sin '
                    'comprobante cargado. No sabemos si está paga.')
            elif p.estado_pago == 'sin_cuotas':
                p.cubre = 'no_se'
                p.motivo_cobertura = _(
                    'Dentro de vigencia, pero no hay ninguna cuota cargada: '
                    'no sabemos si se está pagando.')
            else:
                p.cubre = 'si'
                p.motivo_cobertura = _(
                    'Vigente hasta el %s y con las cuotas confirmadas.'
                ) % p.fecha_fin

    def _search_vigente(self, operator, value):
        hoy = fields.Date.context_today(self)
        dominio = [('fecha_inicio', '<=', hoy), ('fecha_fin', '>=', hoy)]
        vigentes = self.search(dominio)
        positivo = (operator == '=' and value) or (operator == '!=' and not value)
        return [('id', 'in' if positivo else 'not in', vigentes.ids)]

    def cubre_a(self, member, fecha=None) -> bool:
        """¿Esta póliza cubría a esta persona en esta fecha?

        Se pregunta por fecha y no por "hoy" a propósito: el día que hay un
        accidente, lo que hay que poder contestar es si estaba cubierta
        entonces, no si lo está ahora.
        """
        self.ensure_one()
        fecha = fecha or fields.Date.context_today(self)
        if not (self.fecha_inicio <= fecha <= self.fecha_fin):
            return False
        return any(n.cubria_en(fecha) for n in self.nomina_ids
                   if n.member_id.id == member.id)


class CoopPolizaNomina(models.Model):
    """Una línea por persona y período.

    No es un Many2many de socios: lo que hay que poder contestar seis meses
    después es "¿estaba en la nómina cuando pasó?", y un many2many solo sabe
    el estado de hoy. Dar de baja a alguien no puede borrar que estuvo.
    """
    _name = 'coop.poliza.nomina'
    _description = 'Persona cubierta por una póliza, y desde cuándo'
    _order = 'fecha_alta desc, id desc'

    poliza_id = fields.Many2one('coop.poliza', string='Póliza', required=True,
                                ondelete='cascade')
    member_id = fields.Many2one('coop.member', string='Socio', required=True,
                                ondelete='restrict')
    fecha_alta = fields.Date(string='Alta en la nómina', required=True,
                             default=fields.Date.context_today)
    fecha_baja = fields.Date(
        string='Baja', help='Vacío = sigue en la nómina.')
    comprobante = fields.Many2one(
        'ir.attachment', string='Endoso / comunicación',
        help='Lo que se le mandó a la aseguradora. Es la prueba de que el '
             'alta se pidió, no solo de que alguien la anotó acá.')

    _sql_constraints = [
        ('fechas_coherentes',
         'CHECK(fecha_baja IS NULL OR fecha_baja >= fecha_alta)',
         'La baja de la nómina no puede ser anterior al alta.'),
    ]

    def cubria_en(self, fecha) -> bool:
        self.ensure_one()
        if not self.fecha_alta or self.fecha_alta > fecha:
            return False
        return not self.fecha_baja or self.fecha_baja >= fecha


class CoopPolizaCuota(models.Model):
    """La plata, período a período.

    El estado se CALCULA de si hay comprobante y de la fecha. No es un
    booleano `pagada` que alguien tilda: en tres meses estaría todo tildado y
    la app afirmaría una cobertura que no existe. Es el bug del acta, pero
    mandando a alguien a un andamio.
    """
    _name = 'coop.poliza.cuota'
    _description = 'Cuota de una póliza'
    _order = 'vencimiento'

    poliza_id = fields.Many2one('coop.poliza', string='Póliza', required=True,
                                ondelete='cascade')
    periodo = fields.Char(string='Período', required=True,
                          help='Ej: 2026-09')
    vencimiento = fields.Date(string='Vence', required=True)
    importe = fields.Monetary(string='Importe')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda',
        default=lambda self: self.env.company.currency_id)
    comprobante = fields.Many2one('ir.attachment', string='Comprobante de pago')
    fecha_pago = fields.Date(string='Fecha de pago')
    estado = fields.Selection([
        ('confirmado', 'Confirmado con comprobante'),
        ('sin_confirmar', 'Sin confirmar'),
        ('vencido', 'Vencido'),
    ], string='Estado', compute='_compute_estado', store=True)

    @api.depends('comprobante', 'fecha_pago', 'vencimiento')
    def _compute_estado(self) -> None:
        hoy = fields.Date.context_today(self)
        for c in self:
            # Confirmado exige LAS DOS cosas: un archivo y una fecha. Una
            # fecha sola es alguien diciendo que pagó.
            if c.comprobante and c.fecha_pago:
                c.estado = 'confirmado'
            elif c.vencimiento and c.vencimiento < hoy:
                c.estado = 'vencido'
            else:
                c.estado = 'sin_confirmar'


class CoopPolizaRequisito(models.Model):
    """Qué seguros le piden a esta obra.

    Sin esto solo se puede decir "tenemos estas pólizas", nunca "a esta obra le
    falta el de altura". El requisito es el puente entre la obra y la póliza, y
    es lo que convierte un archivo en una habilitación.
    """
    _name = 'coop.poliza.requisito'
    _description = 'Seguro exigido a una obra'
    _order = 'obra_id, tipo_requerido'

    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True, ondelete='cascade',
        domain=[('is_coop_obra', '=', True)])
    tipo_requerido = fields.Selection(TIPO_POLIZA, string='Seguro exigido',
                                      required=True)
    exigido_por = fields.Selection([
        ('comitente', 'El comitente'),
        ('municipio', 'El municipio'),
        ('ley', 'La ley'),
        ('cooperativa', 'La propia cooperativa'),
    ], string='Lo exige', default='comitente', required=True)
    poliza_id = fields.Many2one(
        'coop.poliza', string='Póliza que lo cubre',
        help='Vacío = el requisito no está satisfecho.')
    fecha_limite = fields.Date(string='Fecha límite')
    satisfecho = fields.Boolean(string='Cumplido',
                                compute='_compute_satisfecho')

    @api.depends('poliza_id', 'poliza_id.cubre')
    def _compute_satisfecho(self) -> None:
        for r in self:
            # Solo 'si'. Un 'no_se' NO satisface un requisito: es justamente
            # el caso en el que no podemos afirmar nada.
            r.satisfecho = bool(r.poliza_id) and r.poliza_id.cubre == 'si'


class CoopCoberturaExcepcion(models.Model):
    """«Arranca igual y nosotros asumimos el riesgo», pero anotado.

    Germán, 2026-08-25: *"la idea es que sin seguro NO... A veces como tarda en
    actualizar hacemos que arranque igual hasta que salga el trámite pero
    nosotros asumimos el riesgo"*.

    Un bloqueo duro se esquivaría por WhatsApp y la app quedaría afuera del
    circuito real, que es la peor salida posible: entonces no se entera de
    nada. Así que la app frena, y si igual deciden arrancar, queda asentado
    QUIÉN asumió el riesgo y HASTA CUÁNDO. Eso convierte una decisión que hoy
    es verbal en un registro, que es lo único que la app puede aportar acá.

    La excepción vence sola. Una excepción sin fecha es un permiso permanente
    con otro nombre.
    """
    _name = 'coop.cobertura.excepcion'
    _description = 'Trabajo autorizado sin cobertura confirmada'
    _order = 'fecha desc, id desc'

    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True, ondelete='cascade',
        domain=[('is_coop_obra', '=', True)])
    member_id = fields.Many2one('coop.member', string='Socio', required=True,
                                ondelete='restrict')
    motivo = fields.Char(string='Por qué se autoriza', required=True)
    autorizado_por_id = fields.Many2one(
        'coop.member', string='Quién asume el riesgo', required=True,
        ondelete='restrict')
    fecha = fields.Date(string='Desde', required=True,
                        default=fields.Date.context_today)
    vence_el = fields.Date(
        string='Vence el', required=True,
        help='Hasta cuándo vale. Una excepción sin vencimiento es un permiso '
             'permanente disfrazado.')
    vigente = fields.Boolean(string='Vigente', compute='_compute_vigente')

    _sql_constraints = [
        ('vence_despues', 'CHECK(vence_el >= fecha)',
         'La excepción no puede vencer antes de empezar.'),
    ]

    @api.depends('fecha', 'vence_el')
    def _compute_vigente(self) -> None:
        hoy = fields.Date.context_today(self)
        for e in self:
            e.vigente = bool(e.fecha and e.vence_el
                             and e.fecha <= hoy <= e.vence_el)


class ProjectProjectSeguros(models.Model):
    _inherit = 'project.project'

    requisito_seguro_ids = fields.One2many(
        'coop.poliza.requisito', 'obra_id', string='Seguros exigidos')

    def cobertura_faltante(self, fecha=None):
        """EL CRUCE. Es la función de todo este módulo.

        Devuelve una lista de problemas concretos: qué persona, en qué obra, y
        qué le falta. Si devuelve vacío es porque no hay nada que reportar, no
        porque no haya mirado.

        Guardar el PDF es archivo. Esto es la función.
        """
        fecha = fecha or fields.Date.context_today(self)
        Poliza = self.env['coop.poliza'].sudo()
        Exc = self.env['coop.cobertura.excepcion'].sudo()
        problemas = []

        for obra in self:
            # 1) Los requisitos de la obra que no están satisfechos.
            for req in obra.requisito_seguro_ids:
                if req.satisfecho:
                    continue
                if req.poliza_id:
                    detalle = _('la póliza %s no cubre: %s') % (
                        req.poliza_id.numero, req.poliza_id.motivo_cobertura)
                else:
                    detalle = _('no hay ninguna póliza asignada')
                problemas.append({
                    'tipo': 'requisito',
                    'obra': obra, 'member': False,
                    'texto': _('%s: falta el seguro de %s — %s') % (
                        obra.name,
                        dict(TIPO_POLIZA).get(req.tipo_requerido,
                                              req.tipo_requerido),
                        detalle),
                })

            # 2) Gente asignada a la obra que no está en ninguna nómina
            #    vigente. Este es el agujero que Germán describió: alguien rota
            #    y nadie lo agrega a la lista.
            nominales = Poliza.search([
                ('sujeto', '=', 'persona'), ('tipo', '=', 'general'),
            ])
            for socio in obra.socio_obra_ids:
                cubierto = any(p.cubre_a(socio, fecha) and p.cubre == 'si'
                               for p in nominales)
                if cubierto:
                    continue
                # ¿Alguien se hizo cargo por escrito?
                exc = Exc.search([
                    ('obra_id', '=', obra.id),
                    ('member_id', '=', socio.id),
                ]).filtered('vigente')
                if exc:
                    problemas.append({
                        'tipo': 'excepcion',
                        'obra': obra, 'member': socio,
                        'texto': _(
                            '%s está en %s sin cobertura confirmada, con '
                            'excepción de %s hasta el %s: %s'
                        ) % (socio.name, obra.name,
                             exc[0].autorizado_por_id.name, exc[0].vence_el,
                             exc[0].motivo),
                    })
                else:
                    problemas.append({
                        'tipo': 'sin_cobertura',
                        'obra': obra, 'member': socio,
                        'texto': _('%s está asignado a %s y no figura en la '
                                   'póliza.') % (socio.name, obra.name),
                    })
        return problemas

    @api.model
    def cruce_diario_cobertura(self):
        """Corre por cron. Devuelve los problemas de TODAS las obras activas.

        Corre todos los días porque la nómina se actualiza por evento —cuando
        alguien se suma se pide la actualización de listas— y no hay un día del
        mes en que alguien revise. El cruce diario no depende de que nadie se
        acuerde. Y cuesta lo mismo con 6 socios que con 60, así que no se apoya
        en que hoy roten poco.
        """
        obras = self.search([('is_coop_obra', '=', True),
                             ('estado_obra', 'in', ['planificacion', 'activa'])])
        return obras.cobertura_faltante()
