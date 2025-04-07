# -*- coding: utf-8 -*-:
from odoo import models, fields


class project_project(models.Model):
    _inherit = "project.project"
    partner_id = fields.Many2one('res.partner')
    partner_plan_descripcion = fields.Char(related="partner_id.plan_descripcion")
    partner_plan_post = fields.Integer(string="Posts", related="partner_id.plan_post")
    partner_plan_historia = fields.Integer(string="Historias", related="partner_id.plan_historia")
    partner_plan_reel = fields.Integer(string="Reels", related="partner_id.plan_reel")
    project_type = fields.Selection(
        selection=[('marketing', 'Marketing'), ('web', 'Web'), ('branding', 'Branding'), ('otro', 'Otro')],
        string='Tipo de Proyecto', required=True,default='marketing')
