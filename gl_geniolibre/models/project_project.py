# -*- coding: utf-8 -*-:
import datetime
import time
import pytz
import requests

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from urllib.parse import urlparse, parse_qs
from collections import defaultdict
from datetime import datetime


class FacebookAdCampaigns(models.Model):
    _name = 'facebook.ad.campaigns'
    _description = 'Facebook Ad Campaigns'
    _sql_constraints = [
        ('campaign_id_unique', 'unique(campaign_id)', 'La campaña ya existe.'),
    ]

    name = fields.Char('Nombre')
    campaign_id = fields.Char('ID de Campaña', required=True)
    account_id = fields.Char('ID Cuenta Publicitaria')
    project_id = fields.Many2one('project.project', string='Proyecto')  # Relación inversa


class project_project(models.Model):
    _inherit = "project.project"
    partner_id = fields.Many2one('res.partner')
    partner_plan_descripcion = fields.Char(related="partner_id.plan_descripcion")
    partner_plan_post = fields.Integer(string="Posts", related="partner_id.plan_post")
    partner_plan_historia = fields.Integer(string="Historias", related="partner_id.plan_historia")
    partner_plan_reel = fields.Integer(string="Reels", related="partner_id.plan_reel")
    project_type = fields.Selection(selection=[
        ('marketing', 'Marketing'),
        ('web', 'Web'),
        ('branding', 'Branding'),
        ('otro', 'Otro')
    ], string='Tipo de Proyecto', required=True, default='marketing')
    partner_page_access_token = fields.Char(related="partner_id.facebook_page_access_token")
    partner_facebook_page_id = fields.Char(related="partner_id.facebook_page_id")
    partner_instagram_page_id = fields.Char(related="partner_id.instagram_page_id")
    partner_tiktok_access_token = fields.Char(related="partner_id.tiktok_access_token")
    partner_id_facebook_ad_account = fields.Char(related="partner_id.id_facebook_ad_account")
    facebook_ad_campaigns_ids = fields.One2many('facebook.ad.campaigns', 'project_id', string='Campañas de Facebook')

    @api.model_create_multi
    def create(self, vals_list):
        # Handle both single create and multi-create cases
        if isinstance(vals_list, dict):
            vals_list = [
                vals_list
            ]

        for vals in vals_list:
            partner_id = vals.get('partner_id')
            project_type = vals.get('project_type')

            if partner_id and project_type:
                existing_project = self.search([
                    ('partner_id', '=', partner_id),
                    ('project_type', '=', project_type)
                ], limit=1)
                if existing_project:
                    raise ValidationError("Ya existe un proyecto para este cliente con el mismo tipo de proyecto.")

        return super(project_project, self).create(vals_list)

    def write(self, vals):
        for record in self:
            partner_id = vals.get('partner_id', record.partner_id.id)
            project_type = vals.get('project_type', record.project_type)

            existing_project = self.search([
                ('id', '!=', record.id),
                ('partner_id', '=', partner_id),
                ('project_type', '=', project_type)
            ], limit=1)

            if existing_project:
                raise ValidationError("Ya existe otro proyecto con este cliente y tipo de proyecto.")

        return super(project_project, self).write(vals)

    def fetch_facebook_campaigns(self):
        # Eliminar todos los registros existentes en el modelo
        self.env['facebook.ad.campaigns'].sudo().search([]).unlink()
        access_token = self.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_key')
        # Get dates (assuming self.date_start and self.date are date/datetime objects)
        since_date = self.date_start
        until_date = self.date

        if not access_token:
            raise ValidationError(f"No existe un token valido")

        # Consulta de campañas de una cuenta
        url = f"https://graph.facebook.com/v22.0/act_{self.partner_id_facebook_ad_account}/campaigns"
        params = {
            'access_token': access_token,
            'fields': 'name,id',
            'effective_status': '["ACTIVE"]',  # << solo campañas activas
            'limit': 1000,  # puedes ajustar si manejas muchas campañas
            'time_range': '{' + f'"since":"{since_date}","until":"{until_date}"' + '}',  # Formato correcto
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise ValidationError(f"Error al obtener campañas de Facebook: {str(response.json())}")

        response.raise_for_status()
        campaigns = response.json().get('data', [])
        Campaign = self.env['facebook.ad.campaigns'].sudo()
        api_ids = [c['id'] for c in campaigns]

        # Crear o actualizar campañas
        for c in campaigns:
            existing = Campaign.search([
                ('campaign_id', '=', c['id'])
            ], limit=1)
            if existing:
                if existing.name != c['name']:
                    existing.write({
                        'name': c['name']
                    })
            else:
                Campaign.create({
                    'name': c['name'],
                    'campaign_id': c['id'],
                    'account_id': self.partner_id_facebook_ad_account,
                })

        # Eliminar campañas que ya no están en la cuenta
        stale = Campaign.search([
            ('account_id', '=', self.partner_id_facebook_ad_account),
            ('campaign_id', 'not in', api_ids),
        ])
        if stale:
            stale.unlink()

    def fetch_google_ads_campaigns(self):
        print("Obtener datos de campañas de Google Ads")

    def get_facebook_data(self, since, until):
        BASE_URL = f"https://graph.facebook.com/v22.0/{self.partner_facebook_page_id}/insights"

        metrics = [
            'page_impressions',
            'page_views_total',
            'page_fans',
            'page_fan_adds',
            'page_fan_removes',
            'page_impressions',
            'page_impressions_unique',
            'page_post_engagements',
            'page_posts_impressions'
        ]
        params = {
            'metric': ','.join(metrics),
            'since': since,
            'until': until,
            'access_token': self.partner_page_access_token,
            'period': 'day',
        }
        all_data = []
        url = BASE_URL
        original_since = int(since)
        original_until = int(until)

        while url:
            response = requests.get(url, params=params if '?' not in url else {}, timeout=10)
            response.raise_for_status()
            result = response.json()
            data = result.get('data', [])
            all_data.extend(data)

            # Obtener siguiente URL
            next_url = result.get('paging', {}).get('next')
            if next_url:
                parsed_url = urlparse(next_url)
                query = parse_qs(parsed_url.query)

                # Convertir a enteros
                next_since = int(query.get('since', [0])[0])
                next_until = int(query.get('until', [9999999999])[0])

                # Validar que aún está dentro del rango original
                if next_since > original_until or next_until > original_until:
                    break

                url = next_url
                params = {}  # Ya no necesitamos `params` porque `next_url` contiene todo
            else:
                url = None

        totals = {}

        for metric in all_data:
            name = metric['name']
            values = metric.get('values', [])
            if name in [
                'page_fans'
            ]:
                totals[name] = values[-1]['value'] if values else 0
            else:
                total_value = sum(entry['value'] for entry in values if isinstance(entry['value'], (int, float)))
                totals[name] = total_value

        post_type_data = defaultdict(lambda: {
            'posts': 0,
            'reach': 0,
            'reactions': 0,
            'comments': 0,
            'shares': 0,
            'pictures': []
        })
        post_url = f"https://graph.facebook.com/v22.0/{self.partner_facebook_page_id}/feed"
        post_params = {
            'fields': 'id,message, shares,attachments,created_time,full_picture,comments.metric(total_count),insights.metric(post_impressions,post_impressions_organic,post_impressions_paid,post_reactions_by_type_total),is_published',
            'since': since,
            'until': until,
            'period': 'day',
            'access_token': self.partner_page_access_token,
        }
        posts_matrix = []

        while post_url:
            post_response = requests.get(post_url, params=post_params, timeout=15)
            post_result = post_response.json()
            posts = post_result.get('data', [])

            for post in posts:
                attachments = post.get('attachments', {}).get('data', [{}])[0]
                post_type = attachments.get('type', 'post').lower()
                insights = post.get('insights', {}).get('data', [])
                comments = post.get('comments', {}).get('data', [])

                insights_dict = {item['name']: item['values'][0]['value'] for item in insights}
                comments_dict = {item['name']: item['values'][0]['value'] for item in comments}

                reach = insights_dict.get('post_impressions', 0)
                organic_reach = insights_dict.get('post_impressions_organic', 0)
                paid_reach = insights_dict.get('post_impressions_paid', 0)

                shares_data = post.get('shares', {})
                total_shares = shares_data.get('count', 0) if isinstance(shares_data, dict) else 0

                comments_data = post.get('comments', {}).get('summary', {})
                total_comments = comments_data.get('total_count', 0)

                reactions_by_type = insights_dict.get('post_reactions_by_type_total', {})
                total_reactions = sum(reactions_by_type.values()) if isinstance(reactions_by_type, dict) else 0

                picture_url = post.get('full_picture', '')
                created_time = post.get('created_time', '')
                post_id = post.get('id', '')
                message = post.get('message', '')

                posts_matrix.append({
                    'type': post_type,
                    'reach': reach,
                    'organic_reach': organic_reach,
                    'paid_reach': paid_reach,
                    'reactions': total_reactions,
                    'reactions_by_type': reactions_by_type,
                    'picture_url': picture_url,
                    'message': message[:50],
                    'created_time': created_time,
                    'post_id': post_id,
                    'comments': total_comments,
                    'shares': total_shares,
                })

                post_type_data[post_type]['posts'] += 1
                post_type_data[post_type]['reach'] += reach
                post_type_data[post_type]['reactions'] += total_reactions
                post_type_data[post_type]['comments'] += total_comments
                post_type_data[post_type]['shares'] += total_shares

            post_url = post_result.get('paging', {}).get('next', '')
            post_params = {}

        # Sección de resultados listos para usar (por ejemplo, en vistas o PDF)
        resumen_por_tipo = {ptype: {
            'posts': data['posts'],
            'reach': data['reach'],
            'reactions': data['reactions'],
            'comments': data['comments'],
            'shares': data['shares'],
        } for ptype, data in post_type_data.items()}

        top_5_posts = sorted(posts_matrix, key=lambda x: x['reach'], reverse=True)[:3]

        return {
            'totals': totals,
            'post_type_summary': resumen_por_tipo,
            'top_posts': top_5_posts,
        }

    def get_instagram_data(self, since, until):
        # 1) Métricas básicas
        original_since = int(since)
        original_until = int(until)
        account_metrics = requests.get(f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}", params={
            'access_token': self.partner_page_access_token,
            'fields': 'followers_count,media_count'
        }, timeout=15).json()

        # Inicializar métricas
        metrics = {
            'reach': 0,
            'profile_views': 0,
            'accounts_engaged': 0,
            'total_interactions': 0,
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'saves': 0,
            'replies': 0,
            'follows_and_unfollows': 0,
            'views': 0,
            'profile_links_taps': 0
        }

        # 2) Request inicial de insights
        base_url = f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}/insights"
        params = {
            'access_token': self.partner_page_access_token,
            'metric': ','.join(metrics.keys()),
            'period': 'day',
            'metric_type': 'total_value',
            'since': since,
            'until': until
        }

        response = requests.get(base_url, params=params, timeout=15)
        result = response.json()
        data_pages = [
            result
        ]
        url = result.get('paging', {}).get('next')

        # 3) Paginación segura
        while url:
            parsed_url = urlparse(url)
            query = parse_qs(parsed_url.query)

            next_since = int(query.get('since', [0])[0])
            next_until = int(query.get('until', [9999999999])[0])

            # Cortamos si el siguiente rango se sale del intervalo
            if next_since > original_until or next_until > original_until:
                break

            response = requests.get(url, timeout=15)
            result = response.json()
            data_pages.append(result)
            url = result.get('paging', {}).get('next')

        # 4) Sumar métricas
        for page in data_pages:
            for metric in page.get('data', []):
                name = metric.get('name')
                if name in metrics:
                    val = metric.get('values') or metric.get('total_value', {})
                    if isinstance(val, list):
                        for entry in val:
                            metrics[name] += entry.get('value', 0)
                    else:
                        metrics[name] += val.get('value', 0)

        # === Estadísticas por tipo de publicación ===
        original_since = int(since)
        original_until = int(until)

        media_url = f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}/media"
        media_params = {
            'access_token': self.partner_page_access_token,
            'fields': ('id,media_type,permalink,media_url,thumbnail_url,caption,timestamp,'
                       'insights.metric('
                       'impressions,reach,views,total_interactions,likes,comments,shares,'
                       'saved,video_views,plays,ig_reels_video_view_total_time,profile_visits'
                       ').period(day)'),
            'since': since,
            'until': until,
            'limit': 100,
        }

        all_media = []
        url = media_url
        params = media_params

        while url:
            response = requests.get(url, params=params if '?' not in url else {}, timeout=15)
            response.raise_for_status()
            result = response.json()
            data = result.get('data', [])
            all_media.extend(data)

            next_url = result.get('paging', {}).get('next')
            if next_url:
                parsed_url = urlparse(next_url)
                query = parse_qs(parsed_url.query)

                next_since = int(query.get('since', [0])[0])
                next_until = int(query.get('until', [9999999999])[0])

                if next_since > original_until or next_until > original_until:
                    break

                url = next_url
                params = {}
            else:
                url = None
        types = [
            'IMAGE',
            'VIDEO',
            'CAROUSEL'
        ]
        summary = {t: {
            'views': 0,
            'reach': 0,
            'total_interactions': 0,
            'likes': 0,
            'comments': 0,
            'shares': 0,
            'saved': 0,
            'video_views': 0,
            'plays': 0,
        } for t in types}

        for post in all_media:
            mtype = post.get('media_type')
            insights = post.get('insights', {}).get('data', [])
            ins = {i['name']: i['values'][0]['value'] for i in insights}
            if mtype in summary:
                for metric in summary[mtype].keys():
                    summary[mtype][metric] += ins.get(metric, 0)
        summary = {k: v for k, v in summary.items() if any(val != 0 for val in v.values())}
        posts_with_reach = []
        for post in all_media:
            insights = post.get('insights', {}).get('data', [])
            ins = {i['name']: i['values'][0]['value'] for i in insights}
            posts_with_reach.append({
                'id': post.get('id'),
                'media_type': post.get('media_type'),
                'thumbnail_url': post.get('thumbnail_url'),
                'permalink': post.get('permalink'),
                'media_url': post.get('media_url'),
                'caption': post.get('caption', '')[:50],
                'created_at': post.get('timestamp'),
                'reach': ins.get('reach', 0),
                'impressions': ins.get('impressions', 0),
                'total_interactions': ins.get('total_interactions', 0),
                'likes': ins.get('likes', 0),
                'comments': ins.get('comments', 0),
                'shares': ins.get('shares', 0),
                'saved': ins.get('saved', 0),
                'video_views': ins.get('video_views', 0),
                'plays': ins.get('plays', 0),
                'views': ins.get('views', 0),
            })
        top_posts = sorted(posts_with_reach, key=lambda x: x['reach'], reverse=True)[:3]
        # Aquí puedes retornar o almacenar los resultados
        return {
            'account_metrics': account_metrics,
            'totals': metrics,
            'summary_by_type': summary,
            'top_posts': top_posts,
        }

    def get_meta_ads_data(self, since, until):
        self.ensure_one()

        def _get_ad_creative_image(campaign_id):
            ad_image_url = None
            ads_url = f"https://graph.facebook.com/v22.0/{campaign_id}/ads"
            ads_params = {
                'access_token': self.partner_page_access_token,
                'fields': 'creative',
            }
            ads_response = requests.get(ads_url, params=ads_params).json()
            ads_data = ads_response.get('data', [])

            if not ads_data:
                return None

            # Tomamos solo el primer anuncio
            creative_id = ads_data[0].get('creative', {}).get('id')
            if not creative_id:
                return None

            creative_url = f"https://graph.facebook.com/v22.0/{creative_id}"
            creative_params = {
                'access_token': self.partner_page_access_token,
                'fields': 'object_story_spec,thumbnail_url,image_url'
            }

            creative_response = requests.get(creative_url, params=creative_params).json()
            ad_image_url = creative_response.get('thumbnail_url', {})

            return ad_image_url

        if not self.partner_page_access_token:
            raise ValidationError("No hay Access Token configurado para esta página.")

        if not self.facebook_ad_campaigns_ids or len(self.facebook_ad_campaigns_ids) == 0:
            raise ValidationError("Debe seleccionar al menos una campaña de Facebook para continuar.")

        total_impressions = 0
        total_clicks = 0
        total_spend = 0.0
        total_reach = 0
        total_cost_per_conversion = 0.0
        total_campaigns = 0
        account_currency = 'PEN'  # Valor por defecto
        all_campaigns_data = []
        total_conversaciones = 0
        for campaign in self.facebook_ad_campaigns_ids:
            if not campaign.campaign_id:
                continue

            url = f"https://graph.facebook.com/v22.0/{campaign.campaign_id}"
            time_range_str = f'{{"since":"{self.date_start}","until":"{self.date}"}}'
            params = {
                'access_token': self.partner_page_access_token,
                'fields': f'id,name,status,effective_status,insights.time_range({time_range_str}){{impressions,clicks,spend,reach,frequency,actions,cost_per_conversion,account_currency}}',
            }
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                insights = data.get('insights', {}).get('data', [{}])[0]
                if total_campaigns == 0:
                    account_currency = insights.get('account_currency', 'PEN')

                impressions = float(insights.get('impressions', 0))
                clicks = float(insights.get('clicks', 0))
                spend = float(insights.get('spend', 0))
                reach = float(insights.get('reach', 0))
                frequency = float(insights.get('frequency', 0))
                cost_per_conversion = float(insights.get('cost_per_conversion', 0))

                total_impressions += impressions
                total_clicks += clicks
                total_spend += spend
                total_reach += reach
                total_cost_per_conversion += cost_per_conversion
                total_campaigns += 1

                ctr = (clicks / impressions * 100) if impressions > 0 else 0
                cpp = (spend / reach) if reach > 0 else 0
                cpm = (spend / impressions * 1000) if impressions > 0 else 0
                cpc = (spend / clicks) if clicks > 0 else 0
                thumbnail_url = _get_ad_creative_image(campaign.campaign_id)
                campaign_data = {
                    'campaign_id': data.get('id', ''),
                    'name': data.get('name', ''),
                    'thumbnail_url': thumbnail_url,
                    'status': data.get('status', ''),
                    'effective_status': data.get('effective_status', ''),
                    'account_currency': account_currency,
                    'impressions': int(impressions),
                    'clicks': int(clicks),
                    'spend': round(spend, 2),
                    'reach': int(reach),
                    'frequency': round(frequency, 2),
                    'cost_per_conversion': round(cost_per_conversion, 2),
                    'ctr': round(ctr, 2),
                    'cpp': round(cpp, 2),
                    'cpm': round(cpm, 2),
                    'cpc': round(cpc, 2),
                    'actions': {},

                }

                for action in insights.get('actions', []):
                    action_type = action.get('action_type')
                    print(action_type)
                    action_value = action.get('value', 0)
                    print(action_value)
                    campaign_data['actions'][action_type] = action_value

                    if action_type == 'onsite_conversion.messaging_conversation_started_7d':
                        total_conversaciones += int(action_value)
                        print(total_conversaciones)

                all_campaigns_data.append(campaign_data)

            except requests.exceptions.RequestException:
                continue
            except Exception:
                continue
        print(total_conversaciones)
        if total_campaigns > 0:
            general_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            general_cpm = (total_spend / total_impressions * 1000) if total_impressions > 0 else 0
            general_cpc = (total_spend / total_clicks) if total_clicks > 0 else 0
            general_cpp = (total_spend / total_reach) if total_reach > 0 else 0
            general_frequency = (total_impressions / total_reach) if total_reach > 0 else 0
            avg_cost_per_conversion = (total_cost_per_conversion / total_campaigns) if total_campaigns > 0 else 0
        else:
            general_ctr = general_cpm = general_cpc = general_cpp = general_frequency = avg_cost_per_conversion = 0

        return {
            'summary': {
                'total_campaigns': total_campaigns,
                'account_currency': account_currency,
                'impressions': int(total_impressions),
                'clicks': int(total_clicks),
                'reach': int(total_reach),
                'spend': round(total_spend, 2),
                'ctr': round(general_ctr, 2),
                'cpc': round(general_cpc, 2),
                'cpm': round(general_cpm, 2),
                'cpp': round(general_cpp, 2),
                'frequency': round(general_frequency, 2),
                'total_conversaciones': total_conversaciones,
            },
            'campaigns': all_campaigns_data,
        }

    def get_google_ads_data(self, since, until):
        print("Simulación de error para prueba")

    def action_generate_report(self):
        self.ensure_one()

        facebook_data = {}
        instagram_data = {}
        meta_ads_data = {}
        google_ads_data = {}

        messages = []
        has_errors = False

        try:
            if not (self.partner_facebook_page_id or self.partner_instagram_page_id):
                raise ValidationError("Debe configurar al menos una cuenta de Facebook o Instagram.")

            # Rango de fechas
            since = int(time.mktime(self.date_start.timetuple()))
            end_dt_utc = datetime.combine(self.date, datetime.max.time()).replace(tzinfo=pytz.UTC)
            until = int(end_dt_utc.timestamp())

            # Facebook
            if self.partner_facebook_page_id:
                try:
                    facebook_data = self.get_facebook_data(since, until)
                    messages.append("✅ Facebook: datos obtenidos.")
                except Exception as e:
                    has_errors = True
                    messages.append(f"❌ Facebook: error - {str(e)}")

                try:
                    meta_ads_data = self.get_meta_ads_data(since, until)
                    print(meta_ads_data)
                    messages.append("✅ Meta Ads: datos obtenidos.")
                except Exception as e:
                    has_errors = True
                    messages.append(f"❌ Meta Ads: error - {str(e)}")

            # Instagram
            if self.partner_instagram_page_id:
                try:
                    instagram_data = self.get_instagram_data(since, until)
                    messages.append("✅ Instagram: datos obtenidos.")
                except Exception as e:
                    has_errors = True
                    messages.append(f"❌ Instagram: error - {str(e)}")

            # Google Ads
            if self.partner_id.id_google_ads_account:
                try:
                    google_ads_data = self.get_google_ads_data(since, until)
                    messages.append("✅ Google Ads: datos obtenidos.")
                except Exception as e:
                    has_errors = True
                    messages.append(f"❌ Google Ads: error - {str(e)}")

            # Consolidar datos
            data = {
                'facebook_data': facebook_data,
                'instagram_data': instagram_data,
                'meta_ads_data': meta_ads_data,
                'google_ads_data': google_ads_data,
                'report_period': {
                    'since': self.date_start.strftime('%Y-%m-%d'),
                    'until': self.date.strftime('%Y-%m-%d'),
                },
                'partner_name': self.partner_id.name,
                'partner_id': self.partner_id.id,
            }

            # Si hubo errores, mostrar notificación
            if has_errors:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': "Reporte generado con advertencias",
                        'message': "\n\n".join([msg for msg in messages if "✅" in msg]) + "\n\n".join([msg for msg in
                                                                                                       messages if
                                                                                                       "❌" in msg]),
                        'type': 'warning',
                        'sticky': True,
                    }
                }

            # Guardar datos en la BD
            self.env['gl.social.reports'].create({
                'partner_id': self.partner_id.id,
                'date_start': self.date_start,
                'date_end': self.date,
                'report_generated': not has_errors,
                'data_json': data,
            })

            return self.env.ref('gl_geniolibre.gl_print_marketing_report').report_action(self, data={
                'data': data
            })

        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Error inesperado",
                    "message": f"❌ {str(e)}",
                    "type": "danger",
                    "sticky": True,
                },
            }

def action_print_report(self):
    data = {
        ...
    }  # Tu diccionario de datos
    return {
        'type': 'ir.actions.report',
        'report_name': 'gl_geniolibre.gl_print_marketing_report_template',
        'report_type': 'qweb-pdf',
        'data': {
            'data': data
        },  # Pasar datos en clave 'data'
        'config': False
    }
