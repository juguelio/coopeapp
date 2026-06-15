{
    'name': 'Cooperativa - Branding y UI',
    'version': '18.0.1.0.0',
    'summary': 'Marca coopeapp en el backoffice y el login + limpieza visual',
    'author': 'Coopeapp',
    'category': 'Cooperative',
    'depends': ['web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'coop_ui/static/src/css/backend.css',
        ],
        'web.assets_frontend': [
            'coop_ui/static/src/css/login.css',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
