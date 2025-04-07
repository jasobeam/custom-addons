# -*- coding: utf-8 -*-

from odoo import models, fields, api

class gl_credentials(models.Model):
    _name = "gl.credentials"
    _description = "Permite guardar credenciales de a los contactos"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char("Nombre del Servicio", tracking=True)
    usuario = fields.Char("Usuario", tracking=True)
    password = fields.Char("Contraseña", tracking=True)
    link = fields.Char("Link de Acceso", tracking=True)
    asignado = fields.Boolean("Asignado", tracking=True)
    credenciales_id = fields.Many2one('res.partner', tracking=True)
