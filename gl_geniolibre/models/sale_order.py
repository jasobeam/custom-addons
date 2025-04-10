from odoo import models, fields, api
from odoo.exceptions import ValidationError


class project_task(models.Model):
    _inherit = "sale.order"

