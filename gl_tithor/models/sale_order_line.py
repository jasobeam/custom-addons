from odoo import fields, models, api


class SaleOrderLine(models.Model):
    """Inherits the model sale.order.line to add a field"""
    _inherit = 'sale.order.line'

    order_line_image = fields.Binary(string="Imagen",
                                     related="product_id.image_1920",
                                     help='Imagen del producto en la línea de pedido de venta')
    product_template_name = fields.Char(
            string="Nombre de Plantilla",
            compute='_compute_product_template_name',
            store=True
        )

    @api.depends('product_id')
    def _compute_product_template_name(self):
        for line in self:
            line.product_template_name = line.product_id.product_tmpl_id.name if line.product_id else False