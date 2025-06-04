# models/whatsapp_chatroom.py
from odoo import models, fields, api


class WhatsappChatroom(models.Model):
    _name = 'whatsapp.chatroom'
    _description = 'WhatsApp Chatroom'
    _rec_name = 'name'

    name = fields.Char(string='Chat Name', required=True)
    phone_number = fields.Char(string='Phone Number', required=True, help="Número de teléfono del cliente.")
    partner_id = fields.Many2one('res.partner', string='Cliente')
    last_message = fields.Text(string='Último Mensaje')
    last_message_time = fields.Datetime(string='Hora del Último Mensaje')
    message_ids = fields.One2many('whatsapp.chatmessage', 'chatroom_id', string='Mensajes')
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('open', 'Abierto'),
        ('closed', 'Cerrado'),
    ], string='Estado', default='open')
    has_partner = fields.Boolean(compute="_compute_has_partner", string="Tiene Cliente")

    @api.depends('partner_id')
    def _compute_has_partner(self):
        for record in self:
            record.has_partner = bool(record.partner_id)

    def set_closed(self):
        for record in self:
            record.state = 'closed'

    def set_open(self):
        for record in self:
            record.state = 'open'


class WhatsappChatMessage(models.Model):
    _name = 'whatsapp.chatmessage'
    _description = 'Mensaje de WhatsApp'
    _order = 'timestamp asc'

    chatroom_id = fields.Many2one('whatsapp.chatroom', string='Chatroom', ondelete='cascade')
    sender = fields.Selection([
                                  ('user', 'Usuario'),
                                  ('bot', 'Bot'),
                                  ('client', 'Cliente')
                              ], string='Remitente')
    message = fields.Text(string='Mensaje')
    timestamp = fields.Datetime(string='Fecha y Hora')
    message_type = fields.Selection([
        ('text', 'Texto'),
        ('image', 'Imagen'),
        ('file', 'Archivo'),
        ('audio', 'Audio'),
        ('video', 'Video'),
    ], string='Tipo de Mensaje', default='text')


class MensajesAutomaticos(models.Model):
    _name = 'mensajes.automaticos'
    _description = 'Mensajes Automáticos para Chatbot'

    name = fields.Char(string='Nombre del Mensaje', required=True)
    contenido = fields.Text(string='Contenido del Mensaje', required=True)
    activo = fields.Boolean(string='Activo', default=True)
    prioridad = fields.Integer(string='Prioridad', default=10)
