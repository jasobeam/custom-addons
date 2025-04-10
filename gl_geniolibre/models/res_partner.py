# -*- coding: utf-8 -*-:
import base64
import hashlib
import random
import time
from datetime import datetime

import requests

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Partner(models.Model):
    _inherit = "res.partner"
    credenciales = fields.One2many('gl.credentials', 'credenciales_id')

    facebook_page_id = fields.Char(string="Facebook Page id", tracking=True)
    facebook_page_access_token = fields.Char(readonly=True)
    instagram_page_id = fields.Char(readonly=True)

    tiktok_auth_code = fields.Char(string="TikTok Auth Code", tracking=True)
    tiktok_access_token = fields.Char(string="TikTok Page id", tracking=True, readonly=True)
    tiktok_refresh_token = fields.Char(readonly=True)
    tiktok_expires_in = fields.Integer(readonly=True)
    tiktok_refresh_expires_in = fields.Integer(readonly=True)
    tiktok_issued_at=fields.Integer(readonly=True)

    code_verifier = fields.Char(readonly=True)
    code_challenge = fields.Char(readonly=True)

    plan_descripcion = fields.Char(string="Plan", tracking=True)
    plan_post = fields.Integer(string="Número de Posts", tracking=True)
    plan_historia = fields.Integer(string="Número de Historias", tracking=True)
    plan_reel = fields.Integer(string="Número de Reels", tracking=True)
    monto = fields.Float(string="Monto a Cobrar", tracking=True)
    publicidad = fields.Float(string="Presupuesto Publicidad", tracking=True)
    moneda = fields.Many2one('res.currency', tracking=True)

    def facebook_obtener_datos(self):
        if self.facebook_page_id:
            access_token = self.env['ir.config_parameter'].sudo()
            page_access_token = access_token.get_param('gl_facebook.api_key')
            print(page_access_token)
            version = 'v22.0'
            # api_url_token = f'https://graph.facebook.com/{version}/{self.facebook_page_id}?fields=access_token&access_token={page_access_token}'

            params = {
                'fields': 'access_token,instagram_business_account',
                'access_token': page_access_token,
            }
            url = f'https://graph.facebook.com/v22.0/{self.facebook_page_id}'
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()  # Raise an exception if the request returns an HTTP error
                data = response.json()
                self.facebook_page_access_token = data['access_token']
                self.instagram_page_id = data['instagram_business_account']['id']
            except requests.exceptions.RequestException as e:
                raise ValidationError(f"Error al publicar en Instagram: {response.json()}")

    def tiktok_get_auth_code(self):
        """
        Simplified version using only json (and Odoo's requests)
        Equivalent to the cURL command but using Odoo's tools
        """
        parametros = self.env['ir.config_parameter'].sudo()
        tiktok_client = parametros.get_param('tiktok_key')
        tiktok_secret = parametros.get_param('tiktok_secret')
        tiktok_redirect = parametros.get_param('tiktok_redirect')
        if not tiktok_client or not tiktok_secret:
            raise ValidationError("No se configuraron las claves de de TikTok")

        # Usage example:
        codigos = generate_code_challenge()
        print(codigos)
        self.write({
            'code_verifier': codigos[0],
            'code_challenge': codigos[1],

        })

        def get_auth_url():
            """ Return the URL to start OAuth flow """
            self.ensure_one()
            base_url = "https://www.tiktok.com/v2/auth/authorize/"
            params = {
                'client_key': tiktok_client,
                'response_type': 'code',
                'scope': 'user.info.basic,video.upload,video.publish',
                'redirect_uri': tiktok_redirect,
                'state': self.id,
                'code_challenge': self.code_challenge,
                'code_challenge_method': 'S256',
                'force_web': 'true'
            }

            auth_url = base_url + "?" + "&".join([f"{k}={v}" for k, v in params.items()])
            return auth_url

        auth_url = get_auth_url()
        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'new',
        }

    def tiktok_renew_token(self):
        parametros = self.env['ir.config_parameter'].sudo()
        tiktok_client = parametros.get_param('tiktok_key')
        tiktok_secret = parametros.get_param('tiktok_secret')


        # Supongamos que guardaste el tiempo en que se emitió y la duración en segundos
        issued_at = self.tiktok_issued_at
        expires_in = self.tiktok_expires_in
        days = 86400 * 1  # 3 días en segundos

        # Calcula el tiempo de expiración y el umbral de renovación
        expiration_time = issued_at + expires_in
        renewal_threshold = expiration_time - days
        # Verifica si ya se necesita renovar
        if time.time() >= renewal_threshold:
            url = "https://open.tiktokapis.com/v2/oauth/token/"

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Cache-Control": "no-cache"
            }

            data = {
                "client_key": tiktok_client,
                "client_secret": tiktok_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.tiktok_refresh_token
            }
            response = requests.post(url, headers=headers, data=data)
            response_data = response.json()
            if response.status_code == 200:
                data = response.json()
                print(data)
                self.write({
                    'tiktok_access_token': data.get('access_token'),
                    'tiktok_expires_in': data.get('expires_in'),
                    'tiktok_refresh_expires_in': data.get('refresh_expires_in'),
                    'tiktok_refresh_token': data.get('refresh_token'),
                    'tiktok_issued_at': int(datetime.now().timestamp()),
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': "El token ha sido actualizado",
                        'type': 'success',
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                raise ValidationError(f"Error al publicar Feed en Facebook: {response_data}")
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': "El token aún es válido.",
                    'type': 'success',
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }


def generate_random_string(length):
    characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
    return ''.join(random.choice(characters) for _ in range(length))

def generate_code_challenge():
    code_verifier = generate_random_string(60)
    sha256_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = sha256_hash.hex()  # Convert to hex string
    return code_verifier, code_challenge