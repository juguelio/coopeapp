{
    'name': 'Cooperativa - Asambleas y Votaciones',
    'version': '18.0.1.0.0',
    'summary': 'Gestión de asambleas, votaciones y actas automáticas para cooperativas',
    'author': 'Plataforma Cooperativa',
    'category': 'Cooperative',
    'license': 'AGPL-3',
    'depends': [
        'coop_members',
        'mail',
    ],
    'data': [
        'security/coop_assembly_security.xml',
        'security/ir.model.access.csv',
        'views/coop_assembly_views.xml',
        'views/coop_vote_views.xml',
        'views/coop_assembly_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
