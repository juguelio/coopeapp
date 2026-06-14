#!/usr/bin/env python3
"""Purga obras demo duplicadas (de corridas viejas), dejando solo la más
nueva. Borra cada obra vieja con todo su árbol de hijos en el orden correcto.

Ejecutar:
    cat scripts/purge_demo_orphans.py | docker compose run --rm -T odoo odoo shell -d coop_piloto
"""
import sys
env = env  # noqa: F821 — inyectado por odoo shell

NOMBRE = 'Obra Piloto San Martín de los Andes'

def borrar(records):
    if records:
        try:
            with env.cr.savepoint():
                records.sudo().unlink()
        except Exception as e:  # noqa: BLE001
            print(f"  (aviso) {records._name}: {e}", file=sys.stderr)

obras = env['project.project'].sudo().search([('name', '=', NOMBRE)], order='id')
if len(obras) <= 1:
    print("No hay obras duplicadas para purgar.", file=sys.stderr)
else:
    viejas = obras[:-1]          # todas menos la más nueva (la del demo actual)
    print(f"Purgando {len(viejas)} obra(s) vieja(s), dejo la más nueva (id={obras[-1].id})",
          file=sys.stderr)
    for o in viejas:
        borrar(env['coop.pedido.material'].sudo().search([('obra_id', '=', o.id)]))
        borrar(env['coop.avance.medicion'].sudo().search([('obra_id', '=', o.id)]))
        borrar(env['coop.foja.item'].sudo().search([('obra_id', '=', o.id)]))
        borrar(env['coop.etapa'].sudo().search([('obra_id', '=', o.id)]))
        borrar(env['coop.certificado'].sudo().search([('obra_id', '=', o.id)]))
        borrar(env['coop.work.entry'].sudo().search([('obra_id', '=', o.id)]))
        borrar(o)
    env.cr.commit()
    print("✓ Orphans purgados.", file=sys.stderr)
