from odoo import api, fields, models
from odoo.exceptions import UserError

from .coop_foja import MEDIDA_TRABAJO


class CoopTrabajoOtro(models.Model):
    """Trabajo que el socio hizo y no entra en ningún ítem de la foja.

    Vive aparte de `coop.avance.medicion` a propósito. La foja es lo que hace
    medible el avance: alimenta el % de obra, la certificación y el %
    productivo. Un texto libre no tiene unidad, así que no puede sumar ahí sin
    romperlo — y teniéndolo en otra tabla eso queda garantizado por
    construcción, no por acordarse de filtrar en cada cómputo.

    Lo que sí cuenta, y es lo que sostiene que el socio cargue, son sus
    jornales y su aporte (`/app/aporte`), que se calculan sobre este modelo
    además del de foja.

    El coordinador lo resuelve: lo mapea a un ítem de foja (y ahí recién se
    vuelve avance certificable), o lo deja registrado sin certificar.
    """
    _name = 'coop.trabajo.otro'
    _description = 'Trabajo del socio sin ítem de foja'
    _order = 'fecha desc, id desc'

    obra_id = fields.Many2one(
        'project.project', string='Obra', required=True,
        domain=[('is_coop_obra', '=', True)], ondelete='restrict')
    member_id = fields.Many2one(
        'coop.member', string='Socio', required=True, ondelete='restrict',
        domain=[('state', '=', 'active')],
        default=lambda self: self.env['coop.member'].search(
            [('partner_id.user_ids', 'in', [self.env.uid])], limit=1))
    fecha = fields.Date(
        string='Fecha', required=True, default=fields.Date.today)
    descripcion = fields.Char(
        string='Qué hizo', required=True,
        help='Lo escribe el socio con sus palabras')
    medida_trabajo = fields.Selection(
        MEDIDA_TRABAJO, string='Medido por', required=True, default='jornal')
    cantidad_trabajo = fields.Float(
        string='Trabajo insumido', required=True, default=1.0,
        help='Jornales, horas o tareas según la unidad de medida elegida')

    state = fields.Selection([
        ('pendiente', 'Pendiente'),
        ('registrado', 'Registrado sin certificar'),
        ('mapeado', 'Mapeado a la foja'),
        ('rechazado', 'Rechazado'),
    ], string='Estado', default='pendiente', required=True)

    avance_id = fields.Many2one(
        'coop.avance.medicion', string='Avance generado', readonly=True,
        ondelete='set null',
        help='El avance de foja que creó el coordinador al mapear esto')
    resuelto_por = fields.Many2one(
        'coop.member', string='Resuelto por', readonly=True)
    nota_coordinador = fields.Char(string='Nota del coordinador')

    _sql_constraints = [
        ('trabajo_positivo', 'CHECK(cantidad_trabajo > 0)',
         'El trabajo insumido debe ser positivo.'),
    ]

    def action_registrar(self, resuelto_por=None, nota=None) -> None:
        """Queda como trabajo registrado: cuenta para los jornales del socio,
        no para la certificación."""
        self.write({
            'state': 'registrado',
            'resuelto_por': resuelto_por.id if resuelto_por else False,
            'nota_coordinador': nota or False,
        })

    def action_rechazar(self, resuelto_por=None, nota=None) -> None:
        self.write({
            'state': 'rechazado',
            'resuelto_por': resuelto_por.id if resuelto_por else False,
            'nota_coordinador': nota or False,
        })

    def action_mapear(self, foja_item, cantidad, resuelto_por=None) -> None:
        """Convierte el trabajo en un avance de foja certificable.

        La cantidad producida la pone el coordinador: el socio nunca la cargó,
        porque cuando cargó no había ítem contra el cual medirla.
        """
        self.ensure_one()
        if self.state == 'mapeado':
            raise UserError('Este trabajo ya está mapeado a la foja.')
        if not foja_item or foja_item.obra_id != self.obra_id:
            raise UserError('El ítem de foja tiene que ser de la misma obra.')
        if cantidad <= 0:
            raise UserError('La cantidad producida tiene que ser positiva.')
        avance = self.env['coop.avance.medicion'].sudo().create({
            'foja_item_id': foja_item.id,
            'member_id': self.member_id.id,
            'fecha': self.fecha,
            'cantidad': cantidad,
            'medida_trabajo': self.medida_trabajo,
            'cantidad_trabajo': self.cantidad_trabajo,
            'state': 'validado',
            'observaciones': self.descripcion,
        })
        self.write({
            'state': 'mapeado', 'avance_id': avance.id,
            'resuelto_por': resuelto_por.id if resuelto_por else False,
        })

    @api.model
    def jornales_de(self, member, medida) -> float:
        """Trabajo que el socio ya cargó y el coordinador no rechazó.

        Se cuenta desde que el coordinador lo resuelve: 'pendiente' todavía no
        es trabajo reconocido, igual que un avance en borrador.
        """
        registros = self.sudo().search([
            ('member_id', '=', member.id),
            ('medida_trabajo', '=', medida),
            ('state', 'in', ['registrado', 'mapeado']),
        ])
        # Lo mapeado ya viaja como avance de foja: sumarlo acá lo contaría dos
        # veces en los jornales del socio.
        return sum(r.cantidad_trabajo for r in registros if not r.avance_id)
