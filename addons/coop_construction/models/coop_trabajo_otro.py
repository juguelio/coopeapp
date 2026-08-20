from odoo import api, fields, models
from odoo.exceptions import UserError

from .coop_foja import MEDIDA_TRABAJO
from .unidades import texto_trabajo  # noqa: F401 — reexport, ver unidades.py


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
    nota_coordinador = fields.Char(
        string='Nota del coordinador',
        help='Obligatoria al rechazar: el socio tiene que saber por qué')
    foto_id = fields.Many2one(
        'ir.attachment', string='Foto', readonly=True, ondelete='set null',
        help='La saca el socio en la obra. Es la única evidencia de lo que '
             'hizo, porque no hay ítem de foja contra el cual medirlo.')
    trabajo_texto = fields.Char(
        string='Trabajo', compute='_compute_trabajo_texto',
        help='Cómo se lee la cantidad en la app: "7 horas", "1 jornal"')

    _sql_constraints = [
        ('trabajo_positivo', 'CHECK(cantidad_trabajo > 0)',
         'El trabajo insumido debe ser positivo.'),
    ]

    @api.depends('cantidad_trabajo', 'medida_trabajo')
    def _compute_trabajo_texto(self) -> None:
        for r in self:
            r.trabajo_texto = texto_trabajo(r.cantidad_trabajo, r.medida_trabajo)

    def action_registrar(self, resuelto_por=None, nota=None) -> None:
        """Queda como trabajo registrado: cuenta para los jornales del socio,
        no para la certificación."""
        self.write({
            'state': 'registrado',
            'resuelto_por': resuelto_por.id if resuelto_por else False,
            'nota_coordinador': (nota or '').strip() or False,
        })

    def guardar_foto(self, archivo, limite_bytes=6 * 1024 * 1024):
        """Guarda la foto del socio como ir.attachment ligado a este registro.

        Devuelve un mensaje de error, o None si salió bien. El límite es la
        última barrera: el navegador ya redimensiona antes de subir, pero un
        cliente viejo o con JS apagado postea el original de la cámara.
        """
        self.ensure_one()
        if not archivo or not getattr(archivo, 'filename', ''):
            return None
        datos = archivo.read()
        if not datos:
            return None
        if len(datos) > limite_bytes:
            return ('La foto pesa %.1f MB y el máximo son %d MB. '
                    'Sacala de nuevo con menos calidad.'
                    % (len(datos) / 1024 / 1024, limite_bytes // 1024 // 1024))
        tipo = (archivo.content_type or '').lower()
        if not tipo.startswith('image/'):
            return 'El archivo tiene que ser una imagen.'
        adjunto = self.env['ir.attachment'].sudo().create({
            'name': archivo.filename,
            'raw': datos,
            'mimetype': tipo,
            'res_model': self._name,
            'res_id': self.id,
        })
        self.sudo().write({'foto_id': adjunto.id})
        return None

    def puede_ver_foto(self, member) -> bool:
        """Ve la foto el socio que la sacó y el capataz de esa obra. Se resuelve
        acá porque los socios no tienen ACL sobre ir.attachment y la ruta sirve
        el binario con sudo."""
        self.ensure_one()
        if not member:
            return False
        if self.member_id.id == member.id:
            return True
        capataz = self.obra_id.capataz_id
        return bool(capataz) and capataz.id == member.id

    def action_rechazar(self, resuelto_por=None, nota=None) -> None:
        """Rechazar EXIGE motivo. Sin esto el socio ve "rechazado" y nada más,
        y no tiene forma de saber qué hacer distinto la próxima vez. Va en el
        modelo y no solo en el controlador para que valga también desde el
        backoffice."""
        motivo = (nota or '').strip()
        if not motivo:
            raise UserError(
                'Para rechazar hay que escribir el motivo: el socio tiene '
                'que saber por qué.')
        self.write({
            'state': 'rechazado',
            'resuelto_por': resuelto_por.id if resuelto_por else False,
            'nota_coordinador': motivo,
        })

    def action_mapear(self, foja_item, cantidad, resuelto_por=None,
                      nota=None) -> None:
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
        vals = {
            'state': 'mapeado', 'avance_id': avance.id,
            'resuelto_por': resuelto_por.id if resuelto_por else False,
        }
        if (nota or '').strip():
            vals['nota_coordinador'] = nota.strip()
        self.write(vals)

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
