# -*- coding: utf-8 -*-
# from odoo import http


# class TestModule(http.Controller):
#     @http.route('/test__module/test__module', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/test__module/test__module/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('test__module.listing', {
#             'root': '/test__module/test__module',
#             'objects': http.request.env['test__module.test__module'].search([]),
#         })

#     @http.route('/test__module/test__module/objects/<model("test__module.test__module"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('test__module.object', {
#             'object': obj
#         })
