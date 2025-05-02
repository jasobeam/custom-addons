from datetime import date

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class gl_social_metric(models.Model):
    _name = 'gl.social.metric'
    _rec_name = 'partner_id'
    _description = 'Resumen mensual de métricas sociales por cliente'

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente',
        required=True
    )

    date_start = fields.Date(string='Fecha Inicial')
    date = fields.Date(string='Fecha Final', index=True, help="Período de fecha del reporte")
    # Credenciales
    partner_id = fields.Many2one('res.partner')

    partner_page_access_token = fields.Char(related="partner_id.facebook_page_access_token")
    partner_facebook_page_id = fields.Char(related="partner_id.facebook_page_id")
    partner_instagram_page_id = fields.Char(related="partner_id.instagram_page_id")
    partner_tiktok_access_token = fields.Char(related="partner_id.tiktok_access_token")

    # FACEBOOK ORGÁNICO
    fb_impressions = fields.Integer(string="Facebook - Impresiones")
    fb_reach = fields.Integer(string="Facebook - Alcance")
    fb_clicks = fields.Integer(string="Facebook - Clics")
    fb_followers = fields.Integer(string="Facebook - Seguidores")
    fb_page_engaged_users = fields.Integer(string="Facebook - Usuarios comprometidos")
    fb_page_views = fields.Integer(string="Facebook - Vistas a la página")
    fb_page_fan_adds = fields.Integer(string="Facebook - Nuevos fans")
    fb_page_fan_removes = fields.Integer(string="Facebook - Pérdidas de fans")

    # FACEBOOK ADS
    fbads_impressions = fields.Integer(string="Facebook Ads - Impresiones")
    fbads_reach = fields.Integer(string="Facebook Ads - Alcance")
    fbads_clicks = fields.Integer(string="Facebook Ads - Clics")
    fbads_spend = fields.Float(string="Facebook Ads - Gasto ($)")
    fbads_cpc = fields.Float(string="Facebook Ads - Costo por clic")
    fbads_ctr = fields.Float(string="Facebook Ads - CTR (%)")
    fbads_video_views = fields.Integer(string="Facebook Ads - Reproducciones de video")
    fbads_thruplays = fields.Integer(string="Facebook Ads - ThruPlays")
    fbads_leads = fields.Integer(string="Facebook Ads - Leads")
    fbads_conversions = fields.Integer(string="Facebook Ads - Conversiones")
    fbads_purchases = fields.Integer(string="Facebook Ads - Compras")
    fbads_add_to_cart = fields.Integer(string="Facebook Ads - Add to Cart")

    # INSTAGRAM ORGÁNICO
    ig_impressions = fields.Integer(string="Instagram - Impresiones")
    ig_reach = fields.Integer(string="Instagram - Alcance")
    ig_clicks = fields.Integer(string="Instagram - Clics")
    ig_followers = fields.Integer(string="Instagram - Seguidores")
    ig_profile_views = fields.Integer(string="Instagram - Vistas al perfil")
    ig_website_clicks = fields.Integer(string="Instagram - Clics al sitio web")
    ig_email_contacts = fields.Integer(string="Instagram - Clicks a email")
    ig_phone_calls = fields.Integer(string="Instagram - Llamadas")
    ig_messages = fields.Integer(string="Instagram - Mensajes")

    # INSTAGRAM ADS
    igads_impressions = fields.Integer(string="Instagram Ads - Impresiones")
    igads_reach = fields.Integer(string="Instagram Ads - Alcance")
    igads_clicks = fields.Integer(string="Instagram Ads - Clics")
    igads_spend = fields.Float(string="Instagram Ads - Gasto ($)")
    igads_cpc = fields.Float(string="Instagram Ads - Costo por clic")
    igads_ctr = fields.Float(string="Instagram Ads - CTR (%)")
    igads_video_views = fields.Integer(string="Instagram Ads - Reproducciones de video")
    igads_thruplays = fields.Integer(string="Instagram Ads - ThruPlays")
    igads_leads = fields.Integer(string="Instagram Ads - Leads")
    igads_conversions = fields.Integer(string="Instagram Ads - Conversiones")
    igads_purchases = fields.Integer(string="Instagram Ads - Compras")
    igads_add_to_cart = fields.Integer(string="Instagram Ads - Add to Cart")

    # TIKTOK ORGÁNICO
    tiktok_impressions = fields.Integer(string="TikTok - Impresiones")
    tiktok_reach = fields.Integer(string="TikTok - Alcance")
    tiktok_clicks = fields.Integer(string="TikTok - Clics")
    tiktok_followers = fields.Integer(string="TikTok - Seguidores")

    # TIKTOK ADS
    tiktokads_impressions = fields.Integer(string="TikTok Ads - Impresiones")
    tiktokads_reach = fields.Integer(string="TikTok Ads - Alcance")
    tiktokads_clicks = fields.Integer(string="TikTok Ads - Clics")
    tiktokads_spend = fields.Float(string="TikTok Ads - Gasto ($)")
    tiktokads_cpc = fields.Float(string="TikTok Ads - Costo por clic")
    tiktokads_ctr = fields.Float(string="TikTok Ads - CTR (%)")
    tiktokads_video_views = fields.Integer(string="TikTok Ads - Reproducciones de video")
    tiktokads_thruplays = fields.Integer(string="TikTok Ads - ThruPlays")
    tiktokads_leads = fields.Integer(string="TikTok Ads - Leads")
    tiktokads_conversions = fields.Integer(string="TikTok Ads - Conversiones")
    tiktokads_purchases = fields.Integer(string="TikTok Ads - Compras")
    tiktokads_add_to_cart = fields.Integer(string="TikTok Ads - Add to Cart")

    # Metadata
    report_generated = fields.Boolean(string="Reporte generado", default=False)

    @api.model_create_multi
    def create(self, vals):
        print("Hello")

