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
# 6. COMMIT + CLEANUP SQL
# ══════════════════════════════════════════════════════════════════

env.cr.commit()

print("\n=== Demo data cargada exitosamente ===", file=sys.stderr)
print("", file=sys.stderr)

# Generar SQL de cleanup (orden inverso por dependencias FK)
cleanup_order = [
    'coop.work.entry',
    'coop.certificado',
    'coop.advance',
    'coop.payroll',
    'coop.vote',
    'coop.assembly',
    'coop.contribution',
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
