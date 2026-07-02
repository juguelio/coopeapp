#!/usr/bin/env python3
"""
PURGA GO-LIVE: borra TODOS los datos de demostración de coopeapp para dejar la
base lista para cargar los datos reales del piloto.

Solo borra lo marcado como demo (email @demo.coop, logins carlos/lucas/sofia/
analia, obra "Obra Piloto San Martín de los Andes", materiales/corralones/
herramientas demo). NO toca configuración, módulos ni datos reales.

Ejecutar (hace un backup ANTES, ver docs/go-live-datos.md):
    cat scripts/purge_demo.py | docker compose run --rm -T odoo odoo shell -d coop_piloto

Es idempotente: se puede correr más de una vez sin error.
"""
import sys
from odoo import fields  # noqa: F401

env = env  # noqa: F821 — inyectado por odoo shell


_avisos = []


def _safe_unlink(records):
    if records:
        try:
            with env.cr.savepoint():
                n = len(records)
                model = records._name
                records.sudo().unlink()
                print("  borradas %d de %s" % (n, model), file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            _avisos.append(records._name)
            print("  (aviso) no se pudo borrar %s: %s" % (records._name, e),
                  file=sys.stderr)


def _search(model, domain):
    if model in env:
        return env[model].sudo().search(domain)
    return env['res.partner'].sudo().browse()


print("=== PURGA GO-LIVE: borrando datos demo ===", file=sys.stderr)

# GUARDA: si ya hay socios reales cargados (partner sin @demo.coop), abortar.
# Este script matchea catálogos por nombre ('Cemento', 'Arena', listas de
# precio de los corralones demo...) y arrasaría datos reales. Solo debe
# correrse ANTES de cargar lo real (paso 2 del runbook go-live-datos.md).
# (total - demo, y no 'not like', porque un email NULL no matchea 'not like')
_reales = (env['coop.member'].sudo().search_count([])
           - env['coop.member'].sudo().search_count(
               [('partner_id.email', 'like', '@demo.coop')]))
if _reales:
    print("!!! ABORTADO: hay %d socios NO-demo en la base. Este script solo "
          "puede correrse antes de cargar datos reales." % _reales,
          file=sys.stderr)
    sys.exit(1)

_demo_partners = env['res.partner'].sudo().search([('email', 'like', '@demo.coop')])
_demo_members = env['coop.member'].sudo().search(
    [('partner_id', 'in', _demo_partners.ids)]) if _demo_partners else \
    env['coop.member'].sudo().browse()
_demo_obras = env['project.project'].sudo().search(
    ['|', ('name', '=', 'Obra Piloto San Martín de los Andes'),
          ('comitente_id', 'in', _demo_partners.ids)])
_demo_users = env['res.users'].sudo().search(
    [('login', 'in', ['carlos', 'lucas', 'sofia', 'analia'])])

# Obras demo con todo su árbol de hijos (orden hijo→padre para no dejar orphans)
for _o in _demo_obras:
    _safe_unlink(_search('coop.incidente', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.asignacion.herramienta', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.orden.corralon', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.acopio', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.pedido.material', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.avance.medicion', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.nota', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.foja.item', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.etapa', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.certificado', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.work.entry', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('project.task', [('project_id', '=', _o.id)]))
    _safe_unlink(_o)

# Catálogos demo
# OJO orden: lista.precio ANTES que material (lista.precio.material_id es
# ondelete='restrict' → si material va primero, el unlink falla y quedan
# materiales demo vivos). Y el dominio va acotado a los corralones demo:
# dominio vacío borraría precios reales si esto se re-corre por accidente.
_safe_unlink(_search('coop.lista.precio', [('corralon_id.name', 'in', [
    'Corralón Austral', 'Corralón El Roble', 'Corralón Don Pedro'])]))
_safe_unlink(_search('coop.material', [('name', 'in', [
    'Cemento', 'Cal hidratada', 'Arena', 'Ladrillo hueco 12x18x33',
    'Hierro aletado 8mm', 'Pintura látex blanca'])]))
_safe_unlink(_search('coop.unidad.produccion', [('name', 'in', [
    'Pintura interior', 'Pintura en altura', 'Mampostería ladrillo hueco',
    'Colocación cañería', 'Contrapiso'])]))
_safe_unlink(_search('coop.corralon', [('name', 'in', [
    'Corralón Austral', 'Corralón El Roble', 'Corralón Don Pedro'])]))

# Pipeline comercial demo + herramientas demo
_safe_unlink(_search('coop.orden.trabajo',
                     [('cliente_id', 'in', _demo_partners.ids)]))
_safe_unlink(_search('maintenance.equipment', [('name', 'like', '(demo)')]))
_safe_unlink(_search('maintenance.equipment.category',
                     [('name', '=', 'Herramientas de obra (demo)')]))

# Movimientos + asambleas demo de los socios demo
if _demo_members:
    _safe_unlink(_search('coop.advance', [('member_id', 'in', _demo_members.ids)]))
    _safe_unlink(_search('coop.payroll', [('member_id', 'in', _demo_members.ids)]))
    _safe_unlink(_search('coop.work.entry', [('member_id', 'in', _demo_members.ids)]))
    _safe_unlink(_search('coop.contribution', [('member_id', 'in', _demo_members.ids)]))
# Asambleas: también por nombre — si una corrida parcial ya borró los members,
# la búsqueda por president/attendee no las encontraría nunca más.
_demo_assemblies = env['coop.assembly'].sudo().search([
    '|', '|',
    ('name', 'in', ['Asamblea Ordinaria - Marzo 2026',
                    'Asamblea Extraordinaria - Junio 2026']),
    ('president_id', 'in', _demo_members.ids),
    ('attendee_ids', 'in', _demo_members.ids)])
if _demo_assemblies:
    _safe_unlink(_search('coop.ballot', [('vote_id.assembly_id', 'in', _demo_assemblies.ids)]))
    _safe_unlink(_search('coop.vote', [('assembly_id', 'in', _demo_assemblies.ids)]))
    _safe_unlink(_search('coop.assembly.point', [('assembly_id', 'in', _demo_assemblies.ids)]))
    _safe_unlink(_search('coop.acta.firma', [('assembly_id', 'in', _demo_assemblies.ids)]))
    _safe_unlink(_demo_assemblies)

# Usuarios → socios → contactos demo (en ese orden)
_safe_unlink(_demo_users)
_safe_unlink(_demo_members)
_safe_unlink(_demo_partners)

env.cr.commit()

# Verificación final HONESTA: contar remanentes de todos los marcadores demo,
# no solo partners. Si hubo avisos o quedó algo, terminar con FAIL visible.
_restos = {
    'partners @demo.coop': env['res.partner'].sudo().search_count(
        [('email', 'like', '@demo.coop')]),
    'obra demo': env['project.project'].sudo().search_count(
        [('name', '=', 'Obra Piloto San Martín de los Andes')]),
    'users demo': env['res.users'].sudo().search_count(
        [('login', 'in', ['carlos', 'lucas', 'sofia', 'analia'])]),
    'materiales demo': len(_search('coop.material', [('name', 'in', [
        'Cemento', 'Cal hidratada', 'Arena', 'Ladrillo hueco 12x18x33',
        'Hierro aletado 8mm', 'Pintura látex blanca'])])),
    'corralones demo': len(_search('coop.corralon', [('name', 'in', [
        'Corralón Austral', 'Corralón El Roble', 'Corralón Don Pedro'])])),
    'herramientas (demo)': len(_search('maintenance.equipment',
                                       [('name', 'like', '(demo)')])),
}
_quedo = {k: v for k, v in _restos.items() if v}
if _avisos or _quedo:
    print("=== PURGA INCOMPLETA ===", file=sys.stderr)
    if _avisos:
        print("  fallaron unlinks en: %s" % ', '.join(sorted(set(_avisos))),
              file=sys.stderr)
    for k, v in _quedo.items():
        print("  quedan %d: %s" % (v, k), file=sys.stderr)
    print("Re-corré el script (es idempotente) o revisá a mano.",
          file=sys.stderr)
    sys.exit(1)
print("=== PURGA COMPLETA. Sin remanentes demo. ===", file=sys.stderr)
