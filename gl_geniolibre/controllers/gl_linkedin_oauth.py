import requests

from odoo import http
from odoo.http import request
from werkzeug.utils import redirect

LinkedIn_Version = "202505"

class LinkedInAuthController(http.Controller):

    @http.route('/linkedin-oauth', type='http', auth='public')
    def linkedin_callback(self, **kwargs):
        code = kwargs.get('code')
        if not code:
            return request.redirect('/web?error=linkedin_auth_failed')

        # Obtener credenciales de la aplicación desde los parámetros del sistema
        client_id = request.env['ir.config_parameter'].sudo().get_param("linkedin.client_id")
        client_secret = request.env['ir.config_parameter'].sudo().get_param("linkedin.client_secret")
        redirect_uri = request.env['ir.config_parameter'].sudo().get_param("linkedin.redirect_uri")

        # Solicitar el token de acceso
        token_url = "https://www.linkedin.com/oauth/v2/accessToken"
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret
        }

        response = requests.post(token_url, data=data)
        if response.status_code != 200:
            return request.redirect('/web?error=linkedin_token_failed')

        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")

        if not access_token:
            return request.redirect('/web?error=linkedin_token_missing')

        # Guardar en ir.config_parameter
        config_param = request.env['ir.config_parameter'].sudo()
        config_param.set_param("linkedin.access_token", access_token)
        config_param.set_param("linkedin.token_expiry", expires_in)

        return redirect('/odoo/settings?#GenioLibre')
