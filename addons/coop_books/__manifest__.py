{
    'name': 'Cooperativa - Libros INAES/IPCyMER',
    'version': '18.0.1.0.0',
    'summary': 'Generación de libros cooperativos para INAES e IPCyMER',
    'depends': ['coop_members', 'coop_assembly', 'coop_payroll', 'account'],
    'data': [
        'security/coop_books_security.xml',
        'security/ir.model.access.csv',
        'report/report_registro_asociados.xml',
        'report/report_actas_asamblea.xml',
        'report/report_actas_consejo.xml',
        'report/report_liquidaciones.xml',
        'report/report_inventario_balance.xml',
        'views/coop_book_export_views.xml',
        'views/coop_book_menus.xml',
    ],
    'installable': True,
    'application': False,
}
