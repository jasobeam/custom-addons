# -*- coding: utf-8 -*-
{
    'name': "GenioLibre - Branding",
    'version': '1.0.1',
    'author': 'GenioLibre',

    'summary': """
        Branding para GenioLibre""",

    'description': """
        Modulo para personalizar el Entorno de Trabajo
    """,

    'website': "GenioLibre.com",
    'application': False,
    'license': 'LGPL-3',
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Customizations',

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'portal', 'base_setup','web','website','sale','sale_management'],

    # always loaded
    'data': [
        'views/gl_branding.xml',
        'views/gl_web_external_layout_folder.xml',
    ],
    "assets": {
        "web.assets_backend": [
            'gl_branding/static/src/js/gl_hide_user_menus.js',
            'gl_branding/static/src/js/gl_web_window_title.js',
        ],
    },
    # only loaded in demonstration mode
    'demo': [

    ],
}