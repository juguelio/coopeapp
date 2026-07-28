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


def _all(model):
    """Accessor único de la purga: SIEMPRE con `active_test=False`.

    En Odoo `search()` esconde los registros archivados por defecto. Para una
    purga eso es exactamente al revés de lo que hace falta: lo archivado es lo
    que más se olvida (una obra que se archiva para sacarla del tablero antes
    de una demo) y por lo tanto lo que sobreviviría al go-live, quedando a la
    vista de la cooperativa real. Todo lo que la purga busque o cuente tiene
    que ver también lo archivado.
    """
    return env[model].sudo().with_context(active_test=False)


def _search(model, domain):
    if model in env:
        return _all(model).search(domain)
    return env['res.partner'].sudo().browse()


print("=== PURGA GO-LIVE: borrando datos demo ===", file=sys.stderr)

# GUARDA: si ya hay socios reales cargados (partner sin @demo.coop), abortar.
# Este script matchea catálogos por nombre ('Cemento', 'Arena', listas de
# precio de los corralones demo...) y arrasaría datos reales. Solo debe
# correrse ANTES de cargar lo real (paso 2 del runbook go-live-datos.md).
# OJO con el email NULL: un socio cargado a mano suele no tener email, y
# 'not like' NO matchea NULL en SQL — hay que preguntar por el vacío aparte.
_no_demo = _all('coop.member').search(
    ['|', ('partner_id.email', '=', False),
          ('partner_id.email', 'not like', '@demo.coop')])
if _no_demo:
    # Nombrar los registros, no solo contarlos: este abort ocurre el día del
    # go-live, con el backup recién hecho y la cooperativa esperando. Saber
    # CUÁL socio bloquea convierte un callejón sin salida en una decisión.
    print("!!! ABORTADO: hay %d socio(s) NO-demo en la base. Este script solo "
          "puede correrse antes de cargar datos reales." % len(_no_demo),
          file=sys.stderr)
    for _m in _no_demo:
        print("      coop.member id=%s · %s · %s" % (
            _m.id, _m.partner_id.display_name,
            _m.partner_id.email or '(sin email)'), file=sys.stderr)
    print("    Si son restos de pruebas manuales, borralos a mano y volvé a "
          "correr. Si son socios reales, NO corras este script.",
          file=sys.stderr)
    sys.exit(1)

_demo_partners = _all('res.partner').search([('email', 'like', '@demo.coop')])
_demo_members = _all('coop.member').search(
    [('partner_id', 'in', _demo_partners.ids)]) if _demo_partners else \
    env['coop.member'].sudo().browse()
_demo_obras = _all('project.project').search(
    ['|', ('name', '=', 'Obra Piloto San Martín de los Andes'),
          ('comitente_id', 'in', _demo_partners.ids)])
_demo_users = _all('res.users').search(
    [('login', 'in', ['carlos', 'lucas', 'sofia', 'analia'])])

# GUARDA 2: obras que la purga NO reconoce como demo.
# Este script solo sabe borrar lo ETIQUETADO (nombre de la obra demo, o
# comitente @demo.coop). Una obra creada a mano desde la app durante las
# pruebas no lleva marcador — y no es que quede como resto inofensivo: sus
# hijos (órdenes al corralón, pedidos) apuntan con FK restrict a los materiales
# y corralones demo, así que impiden borrarlos y la purga termina a mitad de
# camino, con la base medio limpia. Verificado sobre una copia el 2026-07-28.
# Por eso se corta ANTES de borrar nada: media purga es peor que ninguna.
_obras_sueltas = _all('project.project').search([('id', 'not in', _demo_obras.ids)])
if _obras_sueltas:
    print("!!! ABORTADO: hay %d obra(s) que la purga no reconoce como demo:"
          % len(_obras_sueltas), file=sys.stderr)
    for _o in _obras_sueltas:
        print("      project.project id=%s · %s%s" % (
            _o.id, _o.display_name,
            '  [ARCHIVADA]' if not _o.active else ''), file=sys.stderr)
    print("    Si son restos de pruebas, borralas con su árbol de hijos y "
          "volvé a correr. Si alguna es real, NO corras este script.",
          file=sys.stderr)
    sys.exit(1)

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
# La OT no se identifica solo por su cliente: una OT cargada a mano desde la app
# durante las pruebas suele tener un cliente sin marcar (o ninguno), pero SIEMPRE
# queda administrada/relevada por un socio demo. Y `administrador_id` es un FK
# restrict contra coop.member: si esa OT sobrevive, después no se pueden borrar
# los socios demo y la purga termina en PURGA INCOMPLETA.
_demo_ots = _search('coop.orden.trabajo',
                    ['|', '|',
                     ('cliente_id', 'in', _demo_partners.ids),
                     ('administrador_id', 'in', _demo_members.ids),
                     ('relevador_id', 'in', _demo_members.ids)])
if _demo_ots:
    # hijos antes que la OT (mismo criterio que el árbol de la obra)
    _safe_unlink(_search('coop.presupuesto', [('orden_id', 'in', _demo_ots.ids)]))
    _safe_unlink(_search('coop.relevamiento', [('orden_id', 'in', _demo_ots.ids)]))
    _safe_unlink(_search('coop.ot.etapa', [('orden_id', 'in', _demo_ots.ids)]))
    _safe_unlink(_demo_ots)
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
_demo_assemblies = _all('coop.assembly').search([
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
# Odoo cuelga del partner las suscripciones de push del navegador, con FK
# restrict: si alguien aceptó notificaciones probando la PWA con un usuario
# demo, ese registro impide borrar el contacto. Es residuo del navegador, no
# dato de la cooperativa.
_safe_unlink(_search('mail.push.device', [('partner_id', 'in', _demo_partners.ids)]))
_safe_unlink(_demo_partners)

env.cr.commit()

# Verificación final HONESTA: contar remanentes de todos los marcadores demo,
# no solo partners. Si hubo avisos o quedó algo, terminar con FAIL visible.
_restos = {
    'partners @demo.coop': _all('res.partner').search_count(
        [('email', 'like', '@demo.coop')]),
    'obra demo': _all('project.project').search_count(
        [('name', '=', 'Obra Piloto San Martín de los Andes')]),
    'users demo': _all('res.users').search_count(
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
print("=== PURGA COMPLETA. Sin remanentes de los marcadores demo. ===",
      file=sys.stderr)
