# -*- coding: utf-8 -*-
{
    'name': 'Sales Contract and Recurring Invoices',
    'version': '18.0.1.0.0',
    'category': 'Sales,Accounting',
    'summary': """Create sale contracts and recurring invoices.""",
    'description': """This module helps to create sale contracts with recurring 
    invoices and enable to access all sale contracts from website portal.""",
    'author': 'Cybrosys Techno Solutions',
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'website': 'https://www.cybrosys.com',
    'depends': ['sale_management', 'website', 'portal'],
    'data': [
        'security/subscription_contracts_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'report/subscription_contract_reports.xml',
        'views/subscription_contracts_views.xml',
        'views/account_move_views.xml',
        'views/subscription_contracts_templates.xml',
        'report/subscription_contract_templates.xml',
    ],
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
