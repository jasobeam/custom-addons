# -*- coding: utf-8 -*-:
from email.policy import default

import requests

from odoo import fields, models, api
from odoo.exceptions import ValidationError



class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    user_access_token = fields.Char(string="Facebook Access Token", config_parameter="gl_facebook.api_key")
    facebook_app_id = fields.Char(string="Facebook API Key", config_parameter="gl_facebook.app_id")
    facebook_app_secret = fields.Char(string="Facebook APP Secret", config_parameter="gl_facebook.secret")
    facebook_redirect_uri = fields.Char(string="Facebook Redirect URI", config_parameter="facebook_redirect",
                                        default="http://localhost:8018/facebook-auth/")

    aws_access_key = fields.Char(string="AWS Clave de acceso", config_parameter="gl_aws.api_key")
    aws_secret = fields.Char(string="AWS Clave de acceso secreta", config_parameter="gl_aws.secret")

    tiktok_client = fields.Char(string="TikTok Clave de cliente", config_parameter="tiktok_key")
    tiktok_secret = fields.Char(string="TikTok Clave secreta", config_parameter="tiktok_secret")
    tiktok_redirect_uri = fields.Char(string="TikTok Redirect URI", config_parameter="tiktok_redirect",
                                      default="http://localhost:8018/tiktok-auth/")


    def conectar_facebook(self):
        scopes_list = [
            "pages_read_user_content",
            "ads_read",
            "ads_management",
            "publish_video",
            "business_management",
            "pages_show_list",
            "instagram_basic",
            "instagram_content_publish",
            "pages_read_engagement",
            "pages_manage_posts",
            "public_profile",
            "read_insights",
            "instagram_manage_insights"
        ]

        scopes = ",".join(scopes_list)

        auth_url = (
            f"https://www.facebook.com/v22.0/dialog/oauth"
            f"?client_id={self.facebook_app_id}"
            f"&redirect_uri={self.facebook_redirect_uri}"
            f"&scope={scopes}"
        )

        return {
            'type': 'ir.actions.act_url',
            'url': auth_url,
            'target': 'new',
        }
