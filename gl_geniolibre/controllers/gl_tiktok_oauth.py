import datetime

import requests

from odoo import http
from odoo.http import request
from werkzeug.utils import redirect
from datetime import datetime


import logging

_logger = logging.getLogger(__name__)


class gl_tiktok_oauth_controller(http.Controller):

    @http.route('/tiktok-auth', type='http', auth='public', website=True, csrf=False)
    def tiktok_auth_callback(self, **kw):
        """ Handle TikTok OAuth callback """

        code = kw.get('code')
        error = kw.get('error')
        partner_id = kw.get('state')

        if error:
            _logger.error("TikTok OAuth error: %s - %s", error, kw.get('error_description', ''))
            return "Authentication failed. Please check the logs for details."

        if not code:
            return "No authorization code received from TikTok."

        # Store the auth code in the TikTok account
        res_partner = request.env['res.partner'].search([('id', '=', partner_id)], limit=1)

        if res_partner:

            base_url = "https://open.tiktokapis.com/v2/oauth/token/"
            parametros = request.env['ir.config_parameter'].sudo()
            tiktok_client = parametros.get_param('tiktok_key')
            tiktok_secret = parametros.get_param('tiktok_secret')
            tiktok_redirect = parametros.get_param('tiktok_redirect')

            verifier = res_partner.code_verifier
            challenge = res_partner.code_challenge


            payload = {
                'client_key': tiktok_client,
                'client_secret': tiktok_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': tiktok_redirect,
                'code_verifier': verifier,

            }
            print(verifier)
            print(payload)
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Cache-Control': 'no-cache'
            }
            response = requests.post(base_url, headers=headers, data=payload)
            response.raise_for_status()  # Raises exception for 4XX/5XX errors
            data = response.json()
            access_token = data.get('access_token')
            expires_in = data.get('expires_in')
            refresh_token = data.get('refresh_token')
            refresh_expires_in = data.get('refresh_expires_in')
            print(data)

            res_partner.write({'tiktok_auth_code': code})
            res_partner.write({'tiktok_access_token': access_token})
            res_partner.write({'tiktok_expires_in': expires_in})
            res_partner.write({'tiktok_refresh_token': refresh_token})
            res_partner.write({'tiktok_issued_at': int(datetime.now().timestamp())})


            print(code)
            _logger.info("Successfully received TikTok auth code")

            return redirect(f'/web#id={partner_id}&model=res.partner&view_type=form')

        return "No TikTok account configured in Odoo."
