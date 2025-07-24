from odoo import models, fields
from odoo.fields import Datetime


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    date_approve = fields.Datetime(string="Confirmation Date", readonly=False)

    def button_confirm(self):
        for order in self:
            if not order.date_approve:
                order.date_approve = Datetime.now()
        return super(PurchaseOrder, self).button_confirm()
