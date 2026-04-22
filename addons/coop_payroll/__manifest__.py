{
    'name': 'Cooperativa - Liquidaciones a Socios',
    'version': '18.0.1.0.0',
    'summary': 'Liquidación transparente a socios: horas, anticipos y pagos visibles para cada socio',
    'author': 'Plataforma Cooperativa',
    'category': 'Cooperative',
    'license': 'AGPL-3',
    'depends': [
        'coop_members',
        'hr',
        'account',
    ],
    'data': [
        'security/coop_payroll_security.xml',
        'security/ir.model.access.csv',
        'views/coop_payroll_views.xml',
        'views/coop_advance_views.xml',
        'views/coop_payroll_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
