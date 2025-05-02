from datetime import date

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class gl_social_reports(models.Model):
    _name = 'gl.social.reports'
    _rec_name = 'partner_id'
    _description = 'Resumen mensual de métricas sociales por cliente'

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        required=True
    )

    date_start = fields.Date(string='Fecha Inicial')
    date_end = fields.Date(string='Fecha Final', index=True, help="Período de fecha del reporte")
    # Credenciales



    # Metadata
    report_generated = fields.Boolean(string="Reporte generado", default=False)

    @api.model_create_multi
    def create(self, vals):
        print("Hello")

