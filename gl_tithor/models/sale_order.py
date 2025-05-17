import base64
import os

import openpyxl
import tempfile

from odoo import fields, models, api
from odoo.exceptions import ValidationError

class Camiseta_Registro(models.Model):
    _name = 'camiseta.registro'
    _description = 'Registro de camisetas para jugadores'

    nombre_en_camiseta = fields.Char(string='Nombre en Camiseta', required=True)
    numero = fields.Integer(string='Número', required=True)

    tipo = fields.Selection([
        ('camiseta_short', 'Camiseta + Short'),
        ('camiseta', 'Camiseta'),
        ('bividi', 'Bividi')
    ], string='Tipo', default='camiseta_short', required=True)

    talla = fields.Selection([
        ('2', '2'),
        ('4', '4'),
        ('6', '6'),
        ('8', '8'),
        ('10', '10'),
        ('12', '12'),
        ('14', '14'),
        ('16', '16'),
        ('s', 'S'),
        ('m', 'M'),
        ('l', 'L'),
        ('xl', 'XL'),
        ('2xl', '2XL'),
        ('3xl', '3XL'),
    ], string='Talla', required=True, default='m')

    corte = fields.Selection([
        ('varon', 'Varón'),
        ('dama', 'Dama')
    ], string='Corte', required=True, default='varon')

    manga = fields.Selection([
        ('normal', 'Normal'),
        ('larga', 'Larga'),
        ('manga_0', 'Manga 0'),
        ('bividi', 'Bividi')
    ], string='Manga', required=True, default='normal')



    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        ondelete='cascade',
        readonly =True
    )


class SaleOrder(models.Model):
    """Inherits the model sale.order"""
    _inherit = 'sale.order'

    is_image_true = fields.Boolean(string="Is Show Image True",
                                   help="Mostrar imagen en la línea de pedido de venta",
                                   compute="_compute_is_image_true")
    camiseta_registro_ids = fields.One2many(
        'camiseta.registro',
        'sale_order_id',
        string='Detalles de las camisetas'
    )
    archivo_excel = fields.Binary("Archivo Excel", attachment=True)
    archivo_nombre = fields.Char("Nombre del archivo")
    def _compute_is_image_true(self):
        """Method _compute_is_image_true returns True if the Show Image option
        in the sale configuration is true"""
        for rec in self:
            rec.is_image_true = True if rec.env[
                'ir.config_parameter'].sudo().get_param(
                'sale_product_image.is_show_product_image_in_sale_report') else False

    def importar_excel(self):
        if not self.archivo_excel:
            raise ValidationError("Por favor, cargue un archivo Excel (.xlsx).")

        tmp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(base64.b64decode(self.archivo_excel))
                tmp_path = tmp.name

            libro = openpyxl.load_workbook(tmp_path, data_only=True)
            hoja = libro.active

            registros = []
            registros_omitidos = 0

            # Mapa de orden para las tallas
            orden_tallas = {
                '2': 0,
                '4': 1,
                '6': 2,
                '8': 3,
                '10': 4,
                '12': 5,
                '14': 6,
                '16': 7,
                's': 8,
                'm': 9,
                'l': 10,
                'xl': 11,
                '2xl': 12,
                '3xl': 13
            }

            for idx, fila in enumerate(hoja.iter_rows(min_row=2), start=2):
                valores = [celda.value for celda in fila]

                if len(valores) < 7 or not any(valores[1:]):
                    registros_omitidos += 1
                    continue

                nombre = valores[1]
                tipo = valores[2]
                numero = valores[3]
                talla = valores[4]
                corte = valores[5]
                manga = valores[6]

                # Normalización de talla
                if talla is not None:
                    if isinstance(talla, (int, float)):
                        talla = str(int(talla))
                    else:
                        talla = str(talla).strip().lower()
                        if talla not in orden_tallas and talla.isdigit():
                            pass
                        else:
                            talla = talla.lower()

                registros.append({
                    'nombre_en_camiseta': nombre,
                    'numero': numero,
                    'tipo': tipo,
                    'talla': talla,
                    'corte': corte,
                    'manga': manga,
                })

            # Ordenar por talla
            registros_ordenados = sorted(registros, key=lambda r: orden_tallas.get(r['talla'], 999))

            for r in registros_ordenados:
                self.env['camiseta.registro'].create({
                    **r,
                    'sale_order_id': self.id,
                })

            self.archivo_excel = False

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Importación completada',
                    'message': f'{len(registros_ordenados)} camisetas importadas correctamente. '
                               f'{registros_omitidos} filas fueron omitidas por estar incompletas.',
                    'type': 'success',
                    'next': {
                        'type': 'ir.actions.act_window_close'
                    },
                }
            }

        except Exception as e:
            raise ValidationError(f"Error al procesar el archivo: {str(e)}")

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
