from odoo import api, models
from odoo.exceptions import AccessError


class CoopReviewable(models.AbstractModel):
    """Keep review decisions out of the worker's draft-write permission.

    Record rules check the old record on write: allowing a worker to edit a
    draft alone does not prevent them from writing its state to validated.
    """
    _name = 'coop.reviewable'
    _description = 'Control de revisión de trabajo y pedidos'

    _review_fields = frozenset()
    _pending_state = None

    def _check_review_access(self):
        if self.env.su:
            return
        self.check_access_rights('write')
        self.check_access_rule('write')
        if self.env.user.has_group('coop_members.group_coop_manager'):
            return
        if not self.env.user.has_group('coop_members.group_coop_coordinador'):
            raise AccessError('Solo el coordinador o el administrador puede revisar este registro.')
        # Coordinators also inherit the own-draft rule. That must not let them
        # review their own submissions on somebody else's work site.
        for record in self.sudo():
            if self.env.user not in record.obra_id.capataz_id.partner_id.user_ids:
                raise AccessError('Solo podés revisar registros de las obras que coordinás.')

    def _check_submission_obra(self):
        if self.env.su or self.env.user.has_group('coop_members.group_coop_manager'):
            return
        coordinator = self.env.user.has_group('coop_members.group_coop_coordinador')
        for record in self.sudo():
            obra = record.obra_id
            if coordinator and self.env.user in obra.capataz_id.partner_id.user_ids:
                continue
            if (not obra.is_coop_obra
                    or obra.estado_obra not in ('planificacion', 'activa')
                    or record.member_id not in obra.socio_obra_ids
                    or self.env.user not in record.member_id.partner_id.user_ids):
                raise AccessError('Solo podés cargar trabajo o pedidos en tus obras asignadas.')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_submission_obra()
        for record in records:
            if record.state != self._pending_state or any(
                    record[name] for name in self._review_fields):
                record._check_review_access()
        return records

    def write(self, vals):
        if (self._review_fields.intersection(vals) or 'state' in vals
                or ('member_id' in vals and any(
                    r.member_id.id != vals['member_id'] for r in self))):
            self._check_review_access()
        result = super().write(vals)
        if {'obra_id', 'foja_item_id', 'member_id'}.intersection(vals):
            self._check_submission_obra()
        return result
