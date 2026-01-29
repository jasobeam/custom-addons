import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class WhatsAppBotController(http.Controller):

    @http.route('/whatsapp/webhook', type='http', auth='public', csrf=False, methods=['GET'])
    def verify_webhook(self, **kwargs):
        verify_token = request.env['ir.config_parameter'].sudo().get_param('whatsapp.verify_token')
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')

        if mode == 'subscribe' and token == verify_token:
            return request.make_response(challenge, headers=[('Content-Type', 'text/plain')])
        else:
            return request.make_response("Token inválido", status=403)

    @http.route('/whatsapp/webhook', type='json', auth='public', csrf=False, methods=['POST'])
    def whatsapp_webhook_post(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            _logger.info("📨 Webhook recibido de WhatsApp:\n%s", json.dumps(data, indent=2))

            # Opcional: imprimir también en consola si estás en desarrollo
            print("📨 Webhook recibido de WhatsApp:")
            print(json.dumps(data, indent=2))

        except Exception as e:
            _logger.error("❌ Error procesando el webhook: %s", str(e))
            return request.make_response("Error", status=500)

        return request.make_response("OK", status=200)
