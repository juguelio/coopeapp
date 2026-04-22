{
    'name': 'Cooperativa - Gestión de Socios',
    'version': '18.0.1.0.0',
    'summary': 'Gestión de socios cooperativos: altas, bajas, aportes y capital social',
    'description': """
        Módulo de gestión de socios para cooperativas de trabajo.
        Contempla los principios cooperativos de la ACI:
        - Adhesión voluntaria y abierta (estados de socio trazables)
        - Control democrático (flujo de aprobación configurable)
        - Participación económica (aportes y capital social)
        - Autonomía (exportación libre de datos)
    """,
    'author': 'Plataforma Cooperativa',
    'category': 'Cooperative',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'hr',
    ],
    'data': [
        'security/coop_members_security.xml',
        'security/ir.model.access.csv',
        'data/coop_member_data.xml',
        'views/coop_member_views.xml',
        'views/coop_contribution_views.xml',
        'views/coop_member_menus.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
