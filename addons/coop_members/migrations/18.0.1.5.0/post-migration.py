"""`coop.member.phone` pasa a ser related de `partner_id.phone`.

La columna ya existía como Char suelto, así que Odoo la deja como está: no
recalcula un campo cuyo nombre no cambió. Sin esto, los socios cargados antes
quedan con la ficha en blanco para siempre (5 de 6 en el piloto) mientras
entran a la app sin problema, porque el login lee el contacto.

Primero se rescata al contacto cualquier teléfono que solo estuviera en la
ficha del socio, y recién después se alinea la ficha contra el contacto. Al
revés se perdería el dato.
"""


def migrate(cr, version):
    if not version:
        return
    # 1) lo que solo estaba en la ficha del socio sube al contacto
    cr.execute("""
        UPDATE res_partner p
           SET phone = m.phone
          FROM coop_member m
         WHERE m.partner_id = p.id
           AND coalesce(p.phone, '') = ''
           AND coalesce(m.phone, '') <> ''
    """)
    rescatados = cr.rowcount
    # 2) la ficha sigue al contacto, que es lo que lee el login
    cr.execute("""
        UPDATE coop_member m
           SET phone = p.phone
          FROM res_partner p
         WHERE p.id = m.partner_id
           AND m.phone IS DISTINCT FROM p.phone
    """)
    alineados = cr.rowcount
    cr.execute("SELECT count(*) FROM coop_member WHERE coalesce(phone, '') = ''")
    vacios = cr.fetchone()[0]
    print('[coop_members] phone: %d rescatados al contacto, %d fichas '
          'alineadas, %d quedan sin teléfono' % (rescatados, alineados, vacios))
