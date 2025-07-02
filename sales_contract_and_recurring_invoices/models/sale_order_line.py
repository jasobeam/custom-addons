# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrderLine(models.Model):
    """ Add contract reference in sale order line """
    _inherit = 'sale.order.line'

    contract_id = fields.Many2one(
        'subscription.contracts',
        string='Contracts',
        help='For adding Contracts in sale order line')
