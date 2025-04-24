# -*- coding: utf-8 -*-
{
    'name': "TITHOR - Custom Development",
    'version': '1.0.1',
    'author': 'GenioLibre',

    'summary': """
        Tithor Custom""",

    'description': """
        Desarrollo personalizado para gestion de Tithor
    """,

    'website': "Tithor.com",
    'application': True,
    'license': 'LGPL-3',
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Customizations',

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'portal', 'base_setup','web','website','sale','sale_management'],

    # always loaded
    'data': [
        # 'views/gl_sale_order_line_views.xml',
        'views/gl_res_config_settings_views.xml',
        'views/gl_sale_order_line_views.xml',

        'report/gl_sale_pre_quote.xml',
        'report/gl_sale_order_report.xml',
    ],
    "assets": {
        "web.assets_backend": [

        ],
        'web.report_assets_common': [

        ],
    },
    # only loaded in demonstration mode
    'demo': [

    ],
}