{
    'name': 'Cooperativa - Asambleas y Votaciones',
    'version': '18.0.1.2.0',
    'summary': 'Asambleas, votaciones (voto secreto), orden del día por puntos, asistencia self-service y acta legal',
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
