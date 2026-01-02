import requests

from odoo import http
from odoo.http import request
from werkzeug.utils import redirect

import logging

_logger = logging.getLogger(__name__)

API_VERSION = None
class gl_facebook_oauth_controller(http.Controller):

    @http.route('/facebook-auth', type='http', auth='public', website=True, csrf=False)
    def facebook_auth_callback(self, **kw):
        API_VERSION = request.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_version')
        print(API_VERSION)
        """ Handle TikTok OAuth callback """
        # Get AWS and Facebook credentials
        facebook_app_id = request.env['ir.config_parameter'].sudo().get_param('gl_facebook.app_id')
        facebook_secret = request.env['ir.config_parameter'].sudo().get_param('gl_facebook.secret')
        facebook_redirect = request.env['ir.config_parameter'].sudo().get_param('facebook_redirect')
        facebook_api_key= request.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_key')

        code = kw.get('code')
        print(code)
        try:
            # url = (
            #     f"https://graph.facebook.com/V22.0/oauth?"
            #     f"client_id={facebook_app_id}&"
            #     f"redirect_uri={facebook_redirect}&"
            #     f"client_secret={facebook_secret}&"
            #     f"code={code}"
            # )
            # response = requests.get(url, timeout=10)
            # response.raise_for_status()
            #
            url = f"https://graph.facebook.com/{API_VERSION}/oauth/access_token"
            params = {
                'client_id': facebook_app_id,
                'client_secret': facebook_secret,
                'code': code,
                'redirect_uri':facebook_redirect,
            }

            response = requests.get(url, params=params)
            print(response.json())
            access_token = response.json().get('access_token')
            request.env['ir.config_parameter'].sudo().set_param('gl_facebook.api_key', access_token)
            request.env.cr.commit()  # Force commit

            return redirect('/odoo/settings?#GenioLibre')

        except Exception as e:
            _logger.error("Error getting user access token: %s", str(e))
            return False

