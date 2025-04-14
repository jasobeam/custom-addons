from odoo import fields, models, api


class SaleOrderLine(models.Model):
    """Inherits the model sale.order.line to add a field"""
    _inherit = 'sale.order.line'

    order_line_image = fields.Binary(string="Imagen",
                                     related="product_id.image_1920",
                                     help='Imagen del producto en la línea de pedido de venta')
