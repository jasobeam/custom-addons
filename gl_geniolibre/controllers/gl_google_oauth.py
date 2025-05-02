import logging
import requests
from datetime import datetime

from odoo import http
from odoo.http import request
from werkzeug.utils import redirect

_logger = logging.getLogger(__name__)


class gl_google_oauth_controller(http.Controller):

    @http.route('/google-auth', type='http', auth='public', website=True, csrf=False)
    def google_auth_callback(self, **kw):
        """
        Este es el endpoint que Google usará para redirigir al usuario después de la autorización.
        Aquí recibimos el 'code' que Google nos envía y lo intercambiamos por el access_token y refresh_token.
        """
        # Recibir el 'code' de la URL
        code = kw.get('code')
        partner_id = kw.get('partner_id')  # Recuperar el partner_id de los parámetros de la URL

        if not code:
            _logger.error('No se recibió el código de autorización de Google.')
            return "Error: No se recibió el código de autorización."

        # Obtener los parámetros globales de configuración de la aplicación
        google_client_id = request.env['ir.config_parameter'].sudo().get_param('gl_google.client_id')
        google_client_secret = request.env['ir.config_parameter'].sudo().get_param('gl_google.client_secret')
        google_redirect_uri = request.env['ir.config_parameter'].sudo().get_param('gl_google.redirect_uri')

        # URL de intercambio de código de Google
        token_url = 'https://oauth2.googleapis.com/token'

        # Realizar el intercambio de código por tokens
        payload = {
            'code': code,
            'client_id': google_client_id,
            'client_secret': google_client_secret,
            'redirect_uri': google_redirect_uri,
            'grant_type': 'authorization_code',
        }

        response = requests.post(token_url, data=payload)
        if response.status_code != 200:
            _logger.error(f"Error al obtener el token de Google: {response.text}")
            return "Error al obtener el token de Google."

        # Analizar la respuesta JSON para obtener el access_token y refresh_token
        data = response.json()
        access_token = data.get('access_token')
        refresh_token = data.get('refresh_token')

        if not access_token or not refresh_token:
            _logger.error('No se obtuvo el access_token o refresh_token de Google.')
            return "Error: No se obtuvieron los tokens necesarios."

        # Guardar el refresh_token globalmente
        config_params = request.env['ir.config_parameter'].sudo()
        config_params.set_param('gl_google.refresh_token', refresh_token)

        # Guardar también el access_token
        config_params.set_param('gl_google.access_token', access_token)

        # Si no se pasa partner_id, redirigir a alguna vista predeterminada
        return redirect('/odoo/settings?#GenioLibre')