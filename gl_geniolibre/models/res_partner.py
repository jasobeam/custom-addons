# -*- coding: utf-8 -*-:
import base64
import hashlib
import random
import time
import requests

from datetime import datetime
from google.ads.googleads.client import GoogleAdsClient
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class GoogleAdsAccount(models.Model):
    _name = 'google.ads.account'
    _description = 'Cuenta de Google Ads'

    name = fields.Char("Nombre")
    account_id = fields.Char("ID de Cuenta", required=True)


class GoogleSearchConsoleSite(models.Model):
    _name = 'google.search.console.site'
    _description = 'Sitio de Google Search Console'

    name = fields.Char("Nombre del sitio")
    site_url = fields.Char("URL del Sitio", required=True)


class GoogleAnalyticsProperty(models.Model):
    _name = 'google.analytics.property'
    _description = 'Propiedad de Google Analytics GA4'

    name = fields.Char("Nombre de la propiedad")
    property_id = fields.Char("ID de Propiedad", required=True)

class FacebookAdAccount(models.Model):
    _name = 'facebook.ad.account'
    _description = 'Facebook Ad Account'

    name = fields.Char('Name')
    account_id = fields.Char('Account ID')


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
    tiktok_issued_at = fields.Integer(readonly=True)

    code_verifier = fields.Char(readonly=True)
    code_challenge = fields.Char(readonly=True)

    plan_descripcion = fields.Char(string="Plan", tracking=True)
    plan_post = fields.Integer(string="Número de Posts", tracking=True)
    plan_historia = fields.Integer(string="Número de Historias", tracking=True)
    plan_reel = fields.Integer(string="Número de Reels", tracking=True)
    monto = fields.Float(string="Monto a Cobrar", tracking=True)
    publicidad = fields.Float(string="Presupuesto Publicidad", tracking=True)
    moneda = fields.Many2one('res.currency', tracking=True)

    id_facebook_ad_account = fields.Char(string="ID Cuenta Publicitaria",
                                         related='facebook_ad_account.account_id',
                                         readonly=True,  # opcional, si no quieres que el usuario lo modifique
                                         store=True, )
    facebook_ad_account = fields.Many2one(
        'facebook.ad.account',
        string='Cuenta publicitaria de Facebook'
    )
    # Google Ads
    google_ads_account = fields.Many2one('google.ads.account', string='Cuenta de Google Ads')
    id_google_ads_account = fields.Char(string="ID Cuenta Google Ads", related='google_ads_account.account_id',
                                        readonly=True, store=True)

    # Search Console
    gsc_site = fields.Many2one('google.search.console.site', string='Sitio Search Console')
    gsc_site_url = fields.Char(string="URL Search Console", related='gsc_site.site_url', readonly=True, store=True)

    # GA4
    ga4_property = fields.Many2one('google.analytics.property', string='Propiedad GA4')
    ga4_property_id = fields.Char(string="ID Propiedad GA4", related='ga4_property.property_id', readonly=True,
                                  store=True)


    def facebook_obtener_datos(self):

        def fetch_facebook_accounts():
            access_token = self.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_key')

            if not access_token:
                return

            url = f"https://graph.facebook.com/v19.0/me/adaccounts"
            params = {
                'access_token': access_token,
                'fields': 'name,account_id'
            }

            response = requests.get(url, params=params)
            response.raise_for_status()
            accounts = response.json().get('data', [])

            AdAccount = self.env['facebook.ad.account'].sudo()
            api_ids = [acc['account_id'] for acc in accounts]

            # 1) Actualizar o crear
            for acc in accounts:
                existing = AdAccount.search([('account_id', '=', acc['account_id'])], limit=1)
                if existing:
                    if existing.name != acc['name']:
                        existing.write({'name': acc['name']})
                else:
                    AdAccount.create({
                        'name': acc['name'],
                        'account_id': acc['account_id'],
                    })

            # 2) Eliminar las cuentas que ya no existen en Facebook
            stale = AdAccount.search([('account_id', 'not in', api_ids)])
            if stale:
                stale.unlink()

        if self.facebook_page_id:
            access_token = self.env['ir.config_parameter'].sudo()
            page_access_token = access_token.get_param('gl_facebook.api_key')
            version = 'v22.0'
            # api_url_token = f'https://graph.facebook.com/{version}/{self.facebook_page_id}?fields=access_token&access_token={page_access_token}'

            params = {
                'fields': 'access_token,instagram_business_account',
                'access_token': page_access_token,
            }
            url = f'https://graph.facebook.com/v22.0/{self.facebook_page_id}'
            fetch_facebook_accounts()

            try:
                response = requests.get(url, params=params)
                response.raise_for_status()  # Raise an exception if the request returns an HTTP error
                data = response.json()
                self.write({
                    'facebook_page_access_token': data['access_token'],
                })

                if 'instagram_business_account' in data:
                    self.write({

                        'instagram_page_id': data['instagram_business_account']['id'],
                    })



            except requests.exceptions.RequestException as e:
                raise ValidationError(f"Error al obtener Tokens de Facebook: {response.json()}")

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
                'scope': 'user.info.basic,video.upload,video.publish,video.list,user.info.stats',
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

    def _get_google_ads_client(self):
        config_param = self.env["ir.config_parameter"].sudo()
        config = {
            "developer_token": config_param.get_param("gl_google.developer_token"),
            "client_id": config_param.get_param("gl_google.client_id"),
            "client_secret": config_param.get_param("gl_google.client_secret"),
            "refresh_token": config_param.get_param("gl_google.refresh_token"),
            "login_customer_id": config_param.get_param("gl_google.login_customer_id"),  # ← ahora dinámico
            "use_proto_plus": True,
        }
        return GoogleAdsClient.load_from_dict(config)

    def google_obtener_datos(self):
        self.env['google.ads.account'].search([]).unlink()
        self.env['google.search.console.site'].search([]).unlink()
        self.env['google.analytics.property'].search([]).unlink()
        client = self._get_google_ads_client()
        ga_service = client.get_service("GoogleAdsService")

        query = """
                    SELECT
                        customer_client.client_customer,
                        customer_client.descriptive_name,
                        customer_client.level,
                        customer_client.status
                    FROM customer_client
                    WHERE customer_client.level = 1
                      AND customer_client.status = 'ENABLED'
                """

        login_customer_id = self.env["ir.config_parameter"].sudo().get_param("gl_google.login_customer_id")
        response = ga_service.search(customer_id=login_customer_id, query=query)

        account_model = self.env["google.ads.account"].sudo()
        for row in response:
            customer = row.customer_client
            print("==== Cuenta ====")
            print("ID:", customer.client_customer.split("/")[-1])
            print("Nombre:", customer.descriptive_name)
            print("Nivel:", customer.level)
            print("Estado:", customer.status)

            customer_id = customer.client_customer.split("/")[-1]
            name = customer.descriptive_name
            level = customer.level
            status = customer.status
            print("####################")
            if not account_model.search([("account_id", "=", customer_id)]):
                account_model.create({
                    "name": name or f"Cuenta {customer_id}",
                    "account_id": customer_id,
                })

        # for partner in self:
        #     # Borrar registros antiguos
        #     self.env['google.ads.account'].search([]).unlink()
        #     self.env['google.search.console.site'].search([]).unlink()
        #     self.env['google.analytics.property'].search([]).unlink()
        #
        #     # ---------------------
        #     # Google Ads API
        #     # ---------------------
        #     # 1. Obtener credenciales
        #     access_token = self.env['ir.config_parameter'].sudo().get_param('gl_google.access_token')
        #     developer_token = "NgJ6-q9NbZ8UZrfJPA9waQ"
        #
        #
        #     if not access_token or not developer_token:
        #         raise ValidationError("Faltan credenciales (access_token o developer_token)")
        #
        #     # 2. Configurar solicitud
        #     headers = {
        #         "Authorization": f"Bearer {access_token}",
        #         "developer-token": developer_token,
        #         "Content-Type": "application/json"
        #     }
        #
        #     # 3. URL CORRECTA (con guión bajo)
        #     url = "https://googleads.googleapis.com/v14/customers:listAccessibleCustomers"
        #
        #     response = requests.get(url, headers=headers)
        #     response.raise_for_status()  # Verificar errores HTTP
        #
        #     data = response.json()
        #
        #     # 4. Procesar respuesta
        #     return [{
        #         "resource_name": resource,
        #         "customer_id": resource.split("/")[-1]
        #     } for resource in data.get("resourceNames", [])]
        #
        #     # ---------------------
        #     # Google Analytics API (GA4)
        #     # ---------------------
        #     url_ga4 = "https://analyticsadmin.googleapis.com/v1beta/accounts"
        #     res_accounts = requests.get(url_ga4, headers=headers)
        #     if res_accounts.status_code != 200:
        #         raise ValidationError(f"Error al obtener cuentas de GA4:\n{res_accounts.text}")
        #     accounts = res_accounts.json().get('accounts', [])
        #
        #     for acc in accounts:
        #         account_id = acc['name'].split('/')[-1]
        #         url_props = f"https://analyticsadmin.googleapis.com/v1beta/accounts/{account_id}/properties"
        #         res_props = requests.get(url_props, headers=headers)
        #         if res_props.status_code != 200:
        #             raise ValidationError(
        #                 f"Error al obtener propiedades de GA4 para la cuenta {account_id}:\n{res_props.text}")
        #         props = res_props.json().get('properties', [])
        #
        #         for prop in props:
        #             prop_id = prop.get('name', '').split('/')[-1]
        #             self.env['google.analytics.property'].create({
        #                 'name': prop.get('displayName', prop_id),
        #                 'property_id': prop_id,
        #             })

def generate_random_string(length):
    characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
    return ''.join(random.choice(characters) for _ in range(length))


def generate_code_challenge():
    code_verifier = generate_random_string(60)
    sha256_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = sha256_hash.hex()  # Convert to hex string
    return code_verifier, code_challenge
