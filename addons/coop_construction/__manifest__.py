{
    'name': 'Cooperativa - Construcción',
    'version': '18.0.1.0.0',
    'summary': 'Obras, certificados de avance y plantel para cooperativas de construcción',
    'author': 'Coopeapp',
    'depends': ['coop_members', 'coop_payroll', 'project'],
    'data': [
        'security/ir.model.access.csv',
        'views/project_project_views.xml',
        'views/project_task_views.xml',
        'views/coop_certificado_views.xml',
        'views/coop_work_entry_views.xml',
        'views/coop_construction_menus.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
