#!/usr/bin/env python3
"""
Datos de demostración para coopeapp.
Ejecutar con:
    cat scripts/load_demo_data.py | docker compose run --rm odoo odoo shell -d coop_piloto

Para borrar todo lo creado, ejecutar el SQL que imprime al final.
"""
import sys
from datetime import date, datetime, timedelta
from odoo import fields

env = env  # noqa: F841 — inyectado por odoo shell

print("=== Cargando datos de demostración ===", file=sys.stderr)

# ══════════════════════════════════════════════════════════════════
# 0. LIMPIEZA IDEMPOTENTE — borra los datos demo de una corrida previa
#    para poder re-ejecutar el script sin chocar con uniques (DNI, login).
#    Todo lo demo se identifica por marcadores: email @demo.coop,
#    logins carlos/lucas, obra "Obra Piloto San Martín de los Andes".
# ══════════════════════════════════════════════════════════════════

def _safe_unlink(records):
    if records:
        try:
            # savepoint: si el unlink falla, solo se revierte esto —
            # la transacción global sigue usable (no se aborta).
            with env.cr.savepoint():
                records.sudo().unlink()
        except Exception as e:  # noqa: BLE001
            print(f"  (aviso) no se pudo borrar {records._name}: {e}",
                  file=sys.stderr)

def _search(model, domain):
    if model in env:
        return env[model].sudo().search(domain)
    return env['res.partner'].sudo().browse()  # vacío si el modelo no existe

print("--- Limpiando datos demo previos (si los hay) ---", file=sys.stderr)
_demo_partners = env['res.partner'].sudo().search([('email', 'like', '@demo.coop')])
_demo_members = env['coop.member'].sudo().search(
    [('partner_id', 'in', _demo_partners.ids)]) if _demo_partners else \
    env['coop.member'].sudo().browse()
_demo_obras = env['project.project'].sudo().search(
    ['|', ('name', '=', 'Obra Piloto San Martín de los Andes'),
          ('comitente_id', 'in', _demo_partners.ids)])
_demo_users = env['res.users'].sudo().search(
    [('login', 'in', ['carlos', 'lucas', 'sofia', 'analia'])])

# Borrar cada obra demo con TODO su árbol de hijos y la obra, en el mismo
# paso (evita orphans: si la obra no se borra por un FK, se ve en el aviso).
for _o in _demo_obras:
    _safe_unlink(_search('coop.orden.corralon', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.acopio', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.pedido.material', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.avance.medicion', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.foja.item', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.etapa', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.certificado', [('obra_id', '=', _o.id)]))
    _safe_unlink(_search('coop.work.entry', [('obra_id', '=', _o.id)]))
    _safe_unlink(_o)

_safe_unlink(_search('coop.material', [('name', 'in', [
    'Cemento', 'Cal hidratada', 'Arena', 'Ladrillo hueco 12x18x33',
    'Hierro aletado 8mm', 'Pintura látex blanca'])]))
_safe_unlink(_search('coop.unidad.produccion', [('name', 'in', [
    'Pintura interior', 'Pintura en altura', 'Mampostería ladrillo hueco',
    'Colocación cañería', 'Contrapiso'])]))
_safe_unlink(_search('coop.corralon', [('name', 'in', [
    'Corralón Austral', 'Corralón El Roble', 'Corralón Don Pedro'])]))
# OTs del pipeline comercial (cascada: memoria, relevamiento, presupuesto).
# Borrar antes que socios/partners (relevamiento.member_id y cliente_id restrict).
_safe_unlink(_search('coop.orden.trabajo',
                     [('cliente_id', 'in', _demo_partners.ids)]))

if _demo_members:
    _safe_unlink(_search('coop.advance', [('member_id', 'in', _demo_members.ids)]))
    _safe_unlink(_search('coop.payroll', [('member_id', 'in', _demo_members.ids)]))
    _safe_unlink(_search('coop.work.entry', [('member_id', 'in', _demo_members.ids)]))
    _safe_unlink(_search('coop.contribution', [('member_id', 'in', _demo_members.ids)]))
    _demo_assemblies = env['coop.assembly'].sudo().search(
        ['|', ('president_id', 'in', _demo_members.ids),
              ('attendee_ids', 'in', _demo_members.ids)])
    _safe_unlink(_search('coop.vote', [('assembly_id', 'in', _demo_assemblies.ids)]))
    _safe_unlink(_demo_assemblies)

_safe_unlink(_demo_users)
_safe_unlink(_demo_members)
_safe_unlink(_demo_partners)
env.cr.commit()
print("--- Limpieza lista ---", file=sys.stderr)


# ── Tracking de IDs para cleanup ──────────────────────────────────
created = {
    'res.partner': [],
    'coop.member': [],
    'coop.contribution': [],
    'coop.assembly': [],
    'coop.vote': [],
    'coop.payroll': [],
    'coop.advance': [],
    'coop.work.entry': [],
    'project.project': [],
    'coop.certificado': [],
}

def track(record):
    created[record._name].extend(record.ids)
    return record


# ══════════════════════════════════════════════════════════════════
# 1. SOCIOS COOPERATIVOS
# ══════════════════════════════════════════════════════════════════

SOCIOS = [
    {
        'name': 'Carlos Martínez',
        'dni': '28456123',
        'cuil': '20-28456123-4',
        'role': 'board',
        'date_admission': date(2023, 3, 15),
        'initial_contribution': 200000.0,
        'email': 'carlos.martinez@demo.coop',
        'phone': '299-4551234',
    },
    {
        'name': 'María Gómez',
        'dni': '31789456',
        'cuil': '27-31789456-8',
        'role': 'board',
        'date_admission': date(2023, 3, 15),
        'initial_contribution': 150000.0,
        'email': 'maria.gomez@demo.coop',
        'phone': '299-4557890',
    },
    {
        'name': 'Lucas Fernández',
        'dni': '33125678',
        'cuil': '20-33125678-5',
        'role': 'worker',
        'date_admission': date(2023, 6, 1),
        'initial_contribution': 100000.0,
        'email': 'lucas.fernandez@demo.coop',
        'phone': '299-4553456',
    },
    {
        'name': 'Sofía Rodríguez',
        'dni': '30567890',
        'cuil': '27-30567890-3',
        'role': 'manager',
        'date_admission': date(2023, 9, 1),
        'initial_contribution': 180000.0,
        'email': 'sofia.rodriguez@demo.coop',
        'phone': '299-4559012',
    },
    {
        'name': 'Diego López',
        'dni': '35234567',
        'cuil': '20-35234567-9',
        'role': 'worker',
        'date_admission': date(2024, 1, 15),
        'initial_contribution': 50000.0,
        'email': 'diego.lopez@demo.coop',
        'phone': '299-4552345',
    },
    {
        'name': 'Analía Suárez',
        'dni': '29876543',
        'cuil': '27-29876543-6',
        'role': 'syndic',
        'date_admission': date(2024, 3, 1),
        'initial_contribution': 120000.0,
        'email': 'analia.suarez@demo.coop',
        'phone': '299-4556789',
    },
]

members = env['coop.member']
Member = env['coop.member'].sudo()
Partner = env['res.partner'].sudo()
Contribution = env['coop.contribution'].sudo()

for s in SOCIOS:
    # red de seguridad: si la limpieza no pudo borrar el socio, reusarlo
    existente = Member.search([('dni', '=', s['dni'])], limit=1)
    if existente:
        existente.write({'state': 'active'})
        members += existente
        continue

    partner = track(Partner.create({
        'name': s['name'],
        'email': s['email'],
        'phone': s['phone'],
        'is_coop_member': True,
        'company_type': 'person',
    }))

    member = track(Member.create({
        'name': s['name'],
        'partner_id': partner.id,
        'dni': s['dni'],
        'cuil': s['cuil'],
        'role': s['role'],
        'state': 'prospect',
        'date_admission': s['date_admission'],
        'initial_contribution': s['initial_contribution'],
    }))

    # Transición a activo
    member.write({'state': 'active'})

    # Aporte inicial confirmado
    contrib = track(Contribution.create({
        'member_id': member.id,
        'name': f"Aporte inicial - {s['name']}",
        'type': 'contribution',
        'amount': s['initial_contribution'],
        'date': s['date_admission'],
        'state': 'draft',
    }))
    contrib.write({'state': 'confirmed'})

    members += member

print(f"  ✓ {len(SOCIOS)} socios creados con aportes iniciales", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════
# 2. ASAMBLEA + VOTACIONES
# ══════════════════════════════════════════════════════════════════

Assembly = env['coop.assembly'].sudo()
Vote = env['coop.vote'].sudo()

# 5 de 6 presentes (Carlos, María, Lucas, Sofía, Diego — falta Analía)
attendees = members[0] | members[1] | members[2] | members[3] | members[4]

assembly = track(Assembly.create({
    'name': 'Asamblea Ordinaria - Marzo 2026',
    'assembly_type': 'ordinary',
    'date': datetime(2026, 3, 15, 18, 0, 0),
    'location': 'Sede social - Neuquén',
    'quorum_required': 50,
    'attendee_ids': [(6, 0, attendees.ids)],
    'president_id': members[0].id,   # Carlos
    'secretary_id': members[1].id,   # María
    'agenda': """
        <ol>
            <li>Aprobación de balance 2025</li>
            <li>Modificación de tarifa horaria</li>
            <li>Compra de herramientas nuevas</li>
        </ol>
    """,
    'state': 'draft',
}))

# Abrir asamblea (valida quórum)
assembly.action_open()

# Votación 1: Aprobación de balance — mayoría simple, 4-1-0, aprobada
vote1 = track(Vote.create({
    'name': 'Aprobación de balance 2025',
    'assembly_id': assembly.id,
    'vote_type': 'simple',
    'sequence': 1,
    'description': 'Aprobación del balance general y estado de resultados del ejercicio 2025.',
    'votes_yes': 4,
    'votes_no': 1,
    'votes_abstain': 0,
    'state': 'pending',
}))
vote1.action_open_vote()
vote1.action_close_vote()

# Votación 2: Tarifa horaria — dos tercios, 4-0-1, aprobada
vote2 = track(Vote.create({
    'name': 'Modificación de tarifa horaria',
    'assembly_id': assembly.id,
    'vote_type': 'two_thirds',
    'sequence': 2,
    'description': 'Incremento de tarifa horaria de $3.500 a $4.200 para obras nuevas.',
    'votes_yes': 4,
    'votes_no': 0,
    'votes_abstain': 1,
    'state': 'pending',
}))
vote2.action_open_vote()
vote2.action_close_vote()

# Votación 3: Herramientas — mayoría simple, 2-3-0, rechazada
vote3 = track(Vote.create({
    'name': 'Compra de herramientas nuevas',
    'assembly_id': assembly.id,
    'vote_type': 'simple',
    'sequence': 3,
    'description': 'Adquisición de herramientas eléctricas por $850.000.',
    'votes_yes': 2,
    'votes_no': 3,
    'votes_abstain': 0,
    'state': 'pending',
}))
vote3.action_open_vote()
vote3.action_close_vote()

# Cerrar asamblea y generar acta
assembly.action_close()
assembly.action_generate_minutes()

print("  ✓ Asamblea con 3 votaciones creada y cerrada", file=sys.stderr)

# ── Asamblea ABIERTA con votaciones abiertas (para votar desde /app) ──
asamblea_viva = track(Assembly.create({
    'name': 'Asamblea Extraordinaria - Junio 2026',
    'assembly_type': 'extraordinary',
    'date': datetime(2026, 6, 15, 10, 0, 0),
    'location': 'Sede social - San Martín de los Andes',
    'quorum_required': 50,
    'attendee_ids': [(6, 0, attendees.ids)],
    'president_id': members[0].id,   # Carlos
    'secretary_id': members[1].id,   # María
    'agenda': '<ol><li>Compra de andamios</li><li>Nuevo coordinador para Quintriqueo</li></ol>',
    'state': 'draft',
}))
asamblea_viva.action_open()

voto_andamios = track(Vote.create({
    'name': 'Compra de andamios nuevos por $4,5M',
    'assembly_id': asamblea_viva.id,
    'vote_type': 'absolute',
    'sequence': 1,
    'description': 'Renovar 12 cuerpos de andamio. Presupuesto en el acta.',
    'state': 'pending',
}))
voto_andamios.action_open_vote()

voto_coord = track(Vote.create({
    'name': 'Designar a Sofía coordinadora de Quintriqueo',
    'assembly_id': asamblea_viva.id,
    'vote_type': 'simple',
    'sequence': 2,
    'description': 'Propuesta del consejo de administración.',
    'state': 'pending',
}))
voto_coord.action_open_vote()

print("  ✓ Asamblea ABIERTA con 2 votaciones para votar en /app", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════
# 3. LIQUIDACIONES MARZO 2026
# ══════════════════════════════════════════════════════════════════

Payroll = env['coop.payroll'].sudo()
Advance = env['coop.advance'].sudo()
WorkEntry = env['coop.work.entry'].sudo()

date_from = date(2026, 3, 1)
date_to = date(2026, 3, 31)

# ── Anticipo para Lucas (se descuenta en su liquidación) ──────────
advance = track(Advance.create({
    'name': 'Anticipo marzo - Lucas Fernández',
    'member_id': members[2].id,   # Lucas
    'amount': 45000.0,
    'date': date(2026, 3, 10),
    'reason': 'Necesidad personal del socio',
    'state': 'draft',
}))
advance.write({'state': 'approved', 'approved_by': env.user.id, 'date_approved': date(2026, 3, 10)})

# ── Liquidación 1: Carlos — 160 horas, sin extras ────────────────
payroll1 = track(Payroll.create({
    'name': 'LIQ-2026-03-001',
    'member_id': members[0].id,
    'date_from': date_from,
    'date_to': date_to,
    'hour_rate': 4200.0,
    'state': 'draft',
}))

# Work entries para Carlos
carlos_hours = [
    (date(2026, 3, 3), 8, 'Replanteo sector B'),
    (date(2026, 3, 4), 8, 'Excavación cimientos'),
    (date(2026, 3, 5), 8, 'Excavación cimientos'),
    (date(2026, 3, 6), 8, 'Armado de encofrado'),
    (date(2026, 3, 7), 8, 'Armado de encofrado'),
    (date(2026, 3, 10), 8, 'Hormigonado bases'),
    (date(2026, 3, 11), 8, 'Hormigonado bases'),
    (date(2026, 3, 12), 8, 'Curado hormigón'),
    (date(2026, 3, 13), 8, 'Albañilería planta baja'),
    (date(2026, 3, 14), 8, 'Albañilería planta baja'),
    (date(2026, 3, 17), 8, 'Albañilería planta baja'),
    (date(2026, 3, 18), 8, 'Instalación cañerías'),
    (date(2026, 3, 19), 8, 'Instalación cañerías'),
    (date(2026, 3, 20), 8, 'Encofrado columnas'),
    (date(2026, 3, 21), 8, 'Encofrado columnas'),
    (date(2026, 3, 24), 8, 'Hormigonado columnas'),
    (date(2026, 3, 25), 8, 'Control de nivel'),
    (date(2026, 3, 26), 8, 'Mampostería exterior'),
    (date(2026, 3, 27), 8, 'Mampostería exterior'),
    (date(2026, 3, 28), 8, 'Limpieza y orden de obra'),
]
for d, h, desc in carlos_hours:
    track(WorkEntry.create({
        'payroll_id': payroll1.id,
        'member_id': members[0].id,
        'date': d,
        'hours': h,
        'description': desc,
        'work_type': 'normal',
        'verified': True,
    }))

payroll1.write({'state': 'review'})
payroll1.write({'member_agrees': True, 'state': 'approved'})
payroll1.write({
    'state': 'paid',
    'date_paid': date(2026, 4, 5),
    'payment_method': 'transfer',
})

# ── Liquidación 2: Lucas — 175 horas, con anticipo descontado ────
payroll2 = track(Payroll.create({
    'name': 'LIQ-2026-03-002',
    'member_id': members[2].id,   # Lucas
    'date_from': date_from,
    'date_to': date_to,
    'hour_rate': 4200.0,
    'advance_ids': [(4, advance.id)],
    'state': 'draft',
}))

lucas_hours = [
    (date(2026, 3, 3), 8, 'Descarga de materiales'),
    (date(2026, 3, 4), 9, 'Excavación zanjas'),
    (date(2026, 3, 5), 8, 'Excavación zanjas'),
    (date(2026, 3, 6), 9, 'Compactación de suelo'),
    (date(2026, 3, 7), 8, 'Armado de hierros'),
    (date(2026, 3, 10), 8, 'Armado de hierros'),
    (date(2026, 3, 11), 9, 'Hormigonado vigas'),
    (date(2026, 3, 12), 8, 'Curado de hormigón'),
    (date(2026, 3, 13), 9, 'Albañilería interior'),
    (date(2026, 3, 14), 8, 'Albañilería interior'),
    (date(2026, 3, 17), 8, 'Revoque grueso'),
    (date(2026, 3, 18), 9, 'Revoque grueso'),
    (date(2026, 3, 19), 8, 'Instalación eléctrica'),
    (date(2026, 3, 20), 8, 'Instalación eléctrica'),
    (date(2026, 3, 21), 9, 'Contrapiso'),
    (date(2026, 3, 24), 8, 'Contrapiso'),
    (date(2026, 3, 25), 8, 'Preparación carpeta'),
    (date(2026, 3, 26), 9, 'Carpeta nivelación'),
    (date(2026, 3, 27), 8, 'Colocación cerámicos'),
    (date(2026, 3, 28), 8, 'Limpieza general'),
    (date(2026, 3, 31), 8, 'Retoque y detalles'),
]
for d, h, desc in lucas_hours:
    track(WorkEntry.create({
        'payroll_id': payroll2.id,
        'member_id': members[2].id,
        'date': d,
        'hours': h,
        'description': desc,
        'work_type': 'normal',
        'verified': True,
    }))

payroll2.write({'state': 'review'})
payroll2.write({'member_agrees': True, 'state': 'approved'})
payroll2.write({
    'state': 'paid',
    'date_paid': date(2026, 4, 5),
    'payment_method': 'transfer',
})

# Marcar anticipo como descontado
advance.write({'state': 'discounted', 'payroll_id': payroll2.id})

# ── Liquidación 3: Diego — 140 horas, con bonificación ───────────
payroll3 = track(Payroll.create({
    'name': 'LIQ-2026-03-003',
    'member_id': members[4].id,   # Diego
    'date_from': date_from,
    'date_to': date_to,
    'hour_rate': 4200.0,
    'bonus_amount': 35000.0,
    'state': 'draft',
}))

diego_hours = [
    (date(2026, 3, 3), 7, 'Preparación de herramientas'),
    (date(2026, 3, 4), 8, 'Movimiento de tierra'),
    (date(2026, 3, 5), 7, 'Movimiento de tierra'),
    (date(2026, 3, 6), 8, 'Asistente de encofrado'),
    (date(2026, 3, 7), 7, 'Asistente de encofrado'),
    (date(2026, 3, 10), 8, 'Mezcla y acarreo'),
    (date(2026, 3, 11), 7, 'Mezcla y acarreo'),
    (date(2026, 3, 12), 8, 'Limpieza de obra'),
    (date(2026, 3, 13), 7, 'Ayudante albañilería'),
    (date(2026, 3, 14), 8, 'Ayudante albañilería'),
    (date(2026, 3, 17), 7, 'Descarga de materiales'),
    (date(2026, 3, 18), 8, 'Corte de ladrillos'),
    (date(2026, 3, 19), 7, 'Pintura de medianeras'),
    (date(2026, 3, 20), 8, 'Pintura de medianeras'),
    (date(2026, 3, 21), 7, 'Acopio y orden'),
    (date(2026, 3, 24), 8, 'Revoque fino interior'),
    (date(2026, 3, 25), 7, 'Revoque fino interior'),
    (date(2026, 3, 26), 8, 'Limpieza final'),
]
for d, h, desc in diego_hours:
    track(WorkEntry.create({
        'payroll_id': payroll3.id,
        'member_id': members[4].id,
        'date': d,
        'hours': h,
        'description': desc,
        'work_type': 'normal',
        'verified': True,
    }))

payroll3.write({'state': 'review'})
payroll3.write({'member_agrees': True, 'state': 'approved'})
payroll3.write({
    'state': 'paid',
    'date_paid': date(2026, 4, 5),
    'payment_method': 'cash',
})

print("  ✓ 3 liquidaciones creadas (1 con anticipo, 1 con bonificación)", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════
# 4. OBRA PILOTO + CERTIFICADOS
# ══════════════════════════════════════════════════════════════════

Project = env['project.project'].sudo()

obra = track(Project.create({
    'name': 'Obra Piloto San Martín de los Andes',
    'is_coop_obra': True,
    'obra_type': 'vivienda',
    'numero_expediente': 'EXP-2026-0042',
    'monto_contrato': 45000000.0,
    'ubicacion': 'Barrio Los Notros - San Martín de los Andes',
    'director_id': members[3].id,    # Sofía (manager)
    'capataz_id': members[0].id,     # Carlos (board/capataz)
    'socio_obra_ids': [(6, 0, [members[0].id, members[2].id, members[4].id])],
    'estado_obra': 'activa',
    'hour_rate': 4200.0,
}))

Certificado = env['coop.certificado'].sudo()

# Certificado 1: 20% avance, cobrado
cert1 = track(Certificado.create({
    'name': 'Certificado Nº1 - Cimientos y bases',
    'obra_id': obra.id,
    'numero': 1,
    'date': date(2026, 1, 31),
    'porcentaje_avance': 20.0,
    'monto_certificado': 9000000.0,
    'state': 'borrador',
}))
cert1.action_presentar()
cert1.action_aprobar()
cert1.action_cobrar()

# Certificado 2: 45% avance acumulado, aprobado
cert2 = track(Certificado.create({
    'name': 'Certificado Nº2 - Estructura y mampostería',
    'obra_id': obra.id,
    'numero': 2,
    'date': date(2026, 2, 28),
    'porcentaje_avance': 45.0,
    'monto_certificado': 11250000.0,
    'state': 'borrador',
}))
cert2.action_presentar()
cert2.action_aprobar()

# Certificado 3: 65% avance acumulado, presentado
cert3 = track(Certificado.create({
    'name': 'Certificado Nº3 - Instalaciones y terminaciones',
    'obra_id': obra.id,
    'numero': 3,
    'date': date(2026, 3, 31),
    'porcentaje_avance': 65.0,
    'monto_certificado': 9000000.0,
    'state': 'borrador',
}))
cert3.action_presentar()

print("  ✓ Obra Piloto con 3 certificados creada", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════
# 5. HORAS TRABAJADAS EN OBRA (20 registros, último mes)
# ══════════════════════════════════════════════════════════════════

# Socios asignados a la obra: Carlos (0), Lucas (2), Diego (4)
obra_workers = [
    (members[0], 'Carlos'),
    (members[2], 'Lucas'),
    (members[4], 'Diego'),
]

obra_entries_data = [
    # Carlos — 7 registros
    (0, date(2026, 3, 24), 8, 'Supervisión hormigonado losa'),
    (0, date(2026, 3, 25), 8, 'Control de nivel y plomada'),
    (0, date(2026, 3, 26), 8, 'Replanteo tabiques interiores'),
    (0, date(2026, 3, 27), 8, 'Supervisión instalación sanitaria'),
    (0, date(2026, 3, 28), 8, 'Coordinación con electricista'),
    (0, date(2026, 3, 31), 8, 'Verificación de avance general'),
    (0, date(2026, 4, 1), 8, 'Preparación certificado Nº3'),
    # Lucas — 7 registros
    (1, date(2026, 3, 24), 9, 'Armado losa — hierro principal'),
    (1, date(2026, 3, 25), 8, 'Armado losa — hierro secundario'),
    (1, date(2026, 3, 26), 9, 'Hormigonado losa'),
    (1, date(2026, 3, 27), 8, 'Curado y apuntalamiento'),
    (1, date(2026, 3, 28), 9, 'Mampostería tabiques'),
    (1, date(2026, 3, 31), 8, 'Mampostería tabiques'),
    (1, date(2026, 4, 1), 8, 'Revoque grueso exterior'),
    # Diego — 6 registros
    (2, date(2026, 3, 24), 8, 'Acarreo hierros a losa'),
    (2, date(2026, 3, 25), 7, 'Mezcla para hormigón'),
    (2, date(2026, 3, 26), 8, 'Vibrado de hormigón'),
    (2, date(2026, 3, 27), 7, 'Limpieza y curado'),
    (2, date(2026, 3, 28), 8, 'Acopio ladrillos planta alta'),
    (2, date(2026, 3, 31), 7, 'Preparación mortero'),
]

for worker_idx, entry_date, hours, desc in obra_entries_data:
    member = obra_workers[worker_idx][0]
    track(WorkEntry.create({
        'member_id': member.id,
        'obra_id': obra.id,
        'date': entry_date,
        'hours': hours,
        'description': desc,
        'work_type': 'normal',
        'verified': True,
    }))

print("  ✓ 20 registros de horas en obra creados", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════
# 5b. DATOS DEL PORTAL (/app): usuario, foja, etapas, avances
# ══════════════════════════════════════════════════════════════════
# Para probar la app de socios end-to-end. Carlos (members[0]) recibe un
# usuario para loguearse; la obra recibe foja de medición y etapas; y se
# cargan avances (validados + uno en borrador) que se ven en /app.

Users = env['res.users'].sudo()
Unidad = env['coop.unidad.produccion'].sudo()
Foja = env['coop.foja.item'].sudo()
Etapa = env['coop.etapa'].sudo()
Avance = env['coop.avance.medicion'].sudo()
Material = env['coop.material'].sudo()
Pedido = env['coop.pedido.material'].sudo()
Corralon = env['coop.corralon'].sudo()

for m in ('coop.unidad.produccion', 'coop.foja.item', 'coop.etapa',
          'coop.avance.medicion', 'coop.material', 'coop.pedido.material',
          'coop.corralon', 'coop.orden.corralon', 'res.users'):
    created.setdefault(m, [])

member_group = env.ref('coop_members.group_coop_member').id
user_group = env.ref('base.group_user').id

def demo_user(member, login, password):
    existing = Users.search([('login', '=', login)], limit=1)
    if existing:
        return existing
    u = track(Users.create({
        'name': member.name, 'login': login, 'password': password,
        'partner_id': member.partner_id.id,
        'groups_id': [(6, 0, [user_group, member_group])],
    }))
    return u

# Carlos (members[0]) es capataz/coordinador de la obra; Lucas (members[2]) socio
carlos = members[0]                       # coordinador (capataz_id de la obra)
lucas = members[2]                        # socio puro
sofia = members[3]                        # administrador (role 'manager')
analia = members[5]                       # síndico (role 'syndic')
demo_user(carlos, 'carlos', 'carlos1234')
demo_user(lucas, 'lucas', 'lucas1234')

# Sofía: administrador → grupo manager (implica member)
if not Users.search([('login', '=', 'sofia')], limit=1):
    track(Users.create({
        'name': sofia.name, 'login': 'sofia', 'password': 'sofia1234',
        'partner_id': sofia.partner_id.id,
        'groups_id': [(6, 0, [
            user_group, env.ref('coop_members.group_coop_manager').id])],
    }))

# Analía: síndico → grupo síndico (implica manager + member)
if not Users.search([('login', '=', 'analia')], limit=1):
    track(Users.create({
        'name': analia.name, 'login': 'analia', 'password': 'analia1234',
        'partner_id': analia.partner_id.id,
        'groups_id': [(6, 0, [
            user_group, env.ref('coop_members.group_coop_syndic').id])],
    }))
print("  ✓ Usuarios portal: carlos (coordinador), lucas (socio), sofia (admin), analia (síndico) — pass <login>1234",
      file=sys.stderr)

# ── Catálogo de unidades de producción ──────────────────────────────
UNIDADES = [
    ('Pintura interior', 'm2', 8500.0),
    ('Pintura en altura', 'm2', 14200.0),
    ('Mampostería ladrillo hueco', 'm2', 32000.0),
    ('Colocación cañería', 'ml', 9800.0),
    ('Contrapiso', 'm2', 18500.0),
]
unidades = {}
for nombre, uom, precio in UNIDADES:
    u = track(Unidad.create({
        'name': nombre, 'uom': uom, 'precio_referencia': precio,
    }))
    unidades[nombre] = u

# ── Foja de medición de la obra ─────────────────────────────────────
FOJA = [
    ('1.0', 'Mampostería planta baja', 'Mampostería ladrillo hueco', 'm2', 180.0, 32000.0),
    ('2.0', 'Contrapiso pasillo', 'Contrapiso', 'm2', 95.0, 18500.0),
    ('3.0', 'Cañería principal', 'Colocación cañería', 'ml', 120.0, 9800.0),
    ('4.0', 'Pintura interior PB', 'Pintura interior', 'm2', 220.0, 8500.0),
    ('5.0', 'Pintura exterior en altura', 'Pintura en altura', 'm2', 160.0, 14200.0),
]
foja_items = {}
for item, nombre, unidad_nombre, uom, cant, precio in FOJA:
    fi = track(Foja.create({
        'obra_id': obra.id,
        'unidad_produccion_id': unidades[unidad_nombre].id,
        'item': item, 'name': nombre, 'uom': uom,
        'cantidad': cant, 'precio_unitario': precio,
    }))
    foja_items[item] = fi

print("  ✓ Foja de medición: 5 ítems con incidencia", file=sys.stderr)

# ── Etapas (1 cerrada, 1 en curso) ──────────────────────────────────
etapa1 = track(Etapa.create({
    'obra_id': obra.id, 'numero': 1, 'name': 'Etapa 1 — Estructura',
    'fecha_certificacion': date(2026, 2, 28), 'ingreso': 18000000.0,
    'saldo_etapa_anterior': 0.0, 'state': 'cerrada',
}))
etapa2 = track(Etapa.create({
    'obra_id': obra.id, 'numero': 2, 'name': 'Etapa 2 — Terminaciones',
    'fecha_certificacion': date(2026, 5, 31), 'ingreso': 27000000.0,
    'saldo_etapa_anterior': 3200000.0, 'state': 'en_curso',
}))
# gastos planificados de la etapa en curso (para que controlador/saldo no sean 0)
for desc, periodo, rubro, importe, est in [
    ('Mano de obra terminaciones', 'mayo', 'mano_obra', 9500000.0, 'pagado'),
    ('Materiales pintura y revoque', 'mayo', 'materiales', 6200000.0, 'pagado'),
    ('Alquiler andamios', 'mayo', 'maquinarias', 1800000.0, 'pendiente'),
]:
    env['coop.proyeccion.gasto'].sudo().create({
        'etapa_id': etapa2.id, 'name': desc, 'periodo': periodo,
        'rubro': rubro, 'importe': importe, 'state': est,
    })

print("  ✓ 2 etapas (1 cerrada, 1 en curso con gastos)", file=sys.stderr)

# ── Avances de medición ─────────────────────────────────────────────
# Lucas (socio) carga; quedan 2 en borrador para que Carlos (coord) valide.
AVANCES = [
    (lucas,  '1.0', 32.0, 'jornal', 1.0, 'validado', date(2026, 5, 20)),
    (lucas,  '4.0', 45.0, 'jornal', 1.0, 'borrador', date(2026, 5, 25)),
    (lucas,  '1.0', 28.0, 'jornal', 1.0, 'borrador', date(2026, 5, 26)),
    (carlos, '3.0', 24.0, 'jornal', 1.0, 'validado', date(2026, 5, 22)),
]
for socio, item, cant, medida, trabajo, estado, fecha in AVANCES:
    av = track(Avance.create({
        'foja_item_id': foja_items[item].id,
        'member_id': socio.id,
        'cantidad': cant, 'medida_trabajo': medida,
        'cantidad_trabajo': trabajo, 'fecha': fecha,
    }))
    if estado == 'validado':
        av.action_validar()

print("  ✓ 4 avances (2 de Lucas en borrador para validar)", file=sys.stderr)

# ── Catálogo de materiales (para que el socio pueda pedir) ──────────
MATERIALES = [
    ('Cemento', 'bolsa', 'bolsa 50kg', '🪨'),
    ('Cal hidratada', 'bolsa', 'bolsa 25kg', '⚪'),
    ('Arena', 'm3', 'm³', '🏖️'),
    ('Ladrillo hueco 12x18x33', 'unidad', 'unidad', '🧱'),
    ('Hierro aletado 8mm', 'barra', 'barra 12m', '🔩'),
    ('Pintura látex blanca', 'lata', 'lata 20L', '🎨'),
]
materiales = {}
for nombre, uom, detalle, icono in MATERIALES:
    mt = track(Material.create({
        'name': nombre, 'uom': uom, 'detalle': detalle, 'icono': icono,
    }))
    materiales[nombre] = mt

# ── Corralones (proveedores de materiales) ──────────────────────────
CORRALONES = [
    ('Corralón Austral', '5492944111222', 'Av. Koessler 1500, SMA'),
    ('Corralón El Roble', '5492944333444', 'Ruta 40 km 2200, SMA'),
    ('Corralón Don Pedro', '5492944555666', 'Pérez 820, SMA'),
]
corralones = {}
for nombre, tel, direccion in CORRALONES:
    c = track(Corralon.create({
        'name': nombre, 'telefono': tel, 'direccion': direccion,
    }))
    corralones[nombre] = c
print("  ✓ 2 corralones (Austral, El Roble)", file=sys.stderr)

# ── Pedidos de Lucas (pendientes, para que Carlos los revise) ───────
PEDIDOS = [
    ('Ladrillo hueco 12x18x33', 500.0, 'mampostería planta baja'),
    ('Pintura látex blanca', 4.0, 'pintura interior'),
]
for nombre, cant, nota in PEDIDOS:
    track(Pedido.create({
        'obra_id': obra.id, 'member_id': lucas.id,
        'material_id': materiales[nombre].id, 'uom': materiales[nombre].uom,
        'cantidad': cant, 'nota': nota,
    }))

# ── Pedidos ya ACEPTADOS, listos para consolidar al corralón ────────
# Dos con corralón asignado (Austral) → /app/corralon muestra un grupo
# listo para "Armar orden"; uno sin corralón → prueba el flujo de asignar.
ACEPTADOS = [
    ('Cemento', 30.0, 'estructura', 'Corralón Austral'),
    ('Arena', 6.0, 'contrapiso', 'Corralón Austral'),
    ('Hierro aletado 8mm', 40.0, 'columnas', None),
]
for nombre, cant, nota, corr in ACEPTADOS:
    ped = track(Pedido.create({
        'obra_id': obra.id, 'member_id': lucas.id,
        'material_id': materiales[nombre].id, 'uom': materiales[nombre].uom,
        'cantidad': cant, 'nota': nota,
    }))
    vals = {'state': 'aceptado', 'revisado_por': carlos.id}
    if corr:
        vals['corralon_id'] = corralones[corr].id
    ped.write(vals)

print("  ✓ Catálogo (6 materiales) + 2 pedidos pendientes + 3 aceptados "
      "(2 con corralón para consolidar)", file=sys.stderr)

# ── Acopios de Austral + listas congeladas + precios actuales (M2) ───
Acopio = env['coop.acopio'].sudo()
AcopioPrecio = env['coop.acopio.precio'].sudo()
ListaPrecio = env['coop.lista.precio'].sudo()
for m in ('coop.acopio', 'coop.acopio.precio', 'coop.lista.precio'):
    created.setdefault(m, [])

# 3 acopios reales de Austral (cronológico: el más viejo = más barato).
# precios congelados por material en cada acopio (ene < abr < jun).
ACOPIOS = [
    ('51584', date(2026, 1, 7), 2770000.0, {
        'Cemento': 7800.0, 'Arena': 42000.0, 'Ladrillo hueco 12x18x33': 480.0,
        'Hierro aletado 8mm': 9500.0, 'Pintura látex blanca': 28000.0,
        'Cal hidratada': 6200.0}),
    ('53683', date(2026, 4, 1), 4750000.0, {
        'Cemento': 9100.0, 'Arena': 49000.0, 'Ladrillo hueco 12x18x33': 560.0,
        'Hierro aletado 8mm': 11200.0, 'Pintura látex blanca': 33000.0,
        'Cal hidratada': 7300.0}),
    ('54073', date(2026, 6, 5), 2531110.0, {
        'Cemento': 10400.0, 'Arena': 55000.0, 'Ladrillo hueco 12x18x33': 640.0,
        'Hierro aletado 8mm': 12800.0, 'Pintura látex blanca': 38000.0,
        'Cal hidratada': 8400.0}),
]
austral = corralones['Corralón Austral']
for numero, fecha, monto, precios in ACOPIOS:
    ac = track(Acopio.create({
        'numero': numero, 'obra_id': obra.id, 'corralon_id': austral.id,
        'fecha': fecha, 'monto_total': monto, 'state': 'vigente',
    }))
    for mat_nombre, precio in precios.items():
        track(AcopioPrecio.create({
            'acopio_id': ac.id, 'material_id': materiales[mat_nombre].id,
            'precio_congelado': precio,
        }))

# Precios actuales (compra directa) de los 3 corralones (~hoy, más caros
# que los congelados → el optimizador va a preferir el acopio).
PRECIOS_ACTUALES = {
    'Corralón Austral':   {'Cemento': 11000.0, 'Arena': 57000.0, 'Ladrillo hueco 12x18x33': 670.0, 'Hierro aletado 8mm': 13500.0, 'Pintura látex blanca': 40000.0, 'Cal hidratada': 8800.0},
    'Corralón El Roble':  {'Cemento': 10800.0, 'Arena': 58000.0, 'Ladrillo hueco 12x18x33': 650.0, 'Hierro aletado 8mm': 13200.0, 'Pintura látex blanca': 41000.0, 'Cal hidratada': 9000.0},
    'Corralón Don Pedro': {'Cemento': 11200.0, 'Arena': 56000.0, 'Ladrillo hueco 12x18x33': 690.0, 'Hierro aletado 8mm': 13250.0, 'Pintura látex blanca': 39500.0, 'Cal hidratada': 8700.0},
}
for corr_nombre, precios in PRECIOS_ACTUALES.items():
    for mat_nombre, precio in precios.items():
        track(ListaPrecio.create({
            'corralon_id': corralones[corr_nombre].id,
            'material_id': materiales[mat_nombre].id,
            'precio': precio, 'fecha': date(2026, 6, 12),
        }))

print("  ✓ 3 acopios Austral (#51584/#53683/#54073) con listas congeladas "
      "+ precios actuales de 3 corralones", file=sys.stderr)

# ── Pipeline comercial (M3): OT + memoria + relevamiento + presupuesto ──
Partner = env['res.partner'].sudo()
OT = env['coop.orden.trabajo'].sudo()
Presup = env['coop.presupuesto'].sudo()
PresupLinea = env['coop.presupuesto.linea'].sudo()
for m in ('coop.orden.trabajo', 'coop.ot.etapa', 'coop.relevamiento',
          'coop.relevamiento.medida', 'coop.presupuesto',
          'coop.presupuesto.linea'):
    created.setdefault(m, [])

cliente = track(Partner.create({
    'name': 'Familia Pérez (cliente demo)',
    'email': 'cliente.perez@demo.coop', 'phone': '5492944999000',
}))
ot = track(OT.create({
    'cliente_id': cliente.id, 'administrador_id': sofia.id,
    'relevador_id': lucas.id,
    'descripcion': 'Refacción de vivienda: baño nuevo y pintura completa.',
    'ubicacion': 'Los Cipreses 340, San Martín de los Andes',
}))
for sec, nombre in [(10, 'Demolición y sanitarios'),
                    (20, 'Albañilería y revoque'),
                    (30, 'Pintura interior y exterior')]:
    track(env['coop.ot.etapa'].sudo().create({
        'orden_id': ot.id, 'secuencia': sec, 'name': nombre}))
# pasa a relevamiento: crea el relevamiento pendiente para Lucas (home card)
ot.action_a_relevamiento()

# presupuesto borrador con líneas por categoría (factura B, IVA incluido)
pres = track(Presup.create({'orden_id': ot.id, 'tipo_factura': 'B'}))
for cat, nombre, cant, precio in [
    ('materiales', 'Cemento, cal y arena (estimado)', 1, 850000.0),
    ('materiales', 'Sanitarios y grifería', 1, 1200000.0),
    ('mano_obra', 'Mano de obra cuadrilla (estimado)', 1, 2400000.0),
    ('logistica', 'Fletes', 2, 90000.0),
]:
    track(PresupLinea.create({
        'presupuesto_id': pres.id, 'categoria': cat, 'name': nombre,
        'cantidad': cant, 'precio_unitario': precio, 'iva_alicuota': '21'}))

print("  ✓ Pipeline M3: 1 OT (Familia Pérez) + memoria 3 etapas + "
      "relevamiento pendiente de Lucas + presupuesto borrador", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════
# 6. COMMIT + CLEANUP SQL
# ══════════════════════════════════════════════════════════════════

env.cr.commit()

print("\n=== Demo data cargada exitosamente ===", file=sys.stderr)
print("", file=sys.stderr)

# Generar SQL de cleanup (orden inverso por dependencias FK)
cleanup_order = [
    'coop.ballot',
    'coop.presupuesto.linea',
    'coop.presupuesto',
    'coop.relevamiento.medida',
    'coop.relevamiento',
    'coop.ot.etapa',
    'coop.orden.trabajo',
    'coop.orden.corralon.linea',
    'coop.orden.corralon',
    'coop.acopio.precio',
    'coop.acopio',
    'coop.lista.precio',
    'coop.pedido.material',
    'coop.corralon',
    'coop.material',
    'coop.avance.medicion',
    'coop.foja.item',
    'coop.etapa',
    'coop.unidad.produccion',
    'coop.work.entry',
    'coop.certificado',
    'coop.advance',
    'coop.payroll',
    'coop.vote',
    'coop.assembly',
    'coop.contribution',
    'res.users',
    'coop.member',
    'project.project',
    'res.partner',
]

print("-- === CLEANUP SQL (guardar por si hay que revertir) ===")
for model_name in cleanup_order:
    ids = created.get(model_name, [])
    if ids:
        table = model_name.replace('.', '_')
        id_list = ', '.join(str(i) for i in ids)
        print(f"DELETE FROM {table} WHERE id IN ({id_list});")
print("-- === FIN CLEANUP ===")
