# -*- coding: utf-8 -*-:
import json
import time

import requests
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from collections import defaultdict


class FacebookAdCampaigns(models.Model):  # Elimina la 's' para consistencia
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
    project_type = fields.Selection(
        selection=[('marketing', 'Marketing'), ('web', 'Web'), ('branding', 'Branding'), ('otro', 'Otro')],
        string='Tipo de Proyecto', required=True, default='marketing')

    partner_page_access_token = fields.Char(related="partner_id.facebook_page_access_token")
    partner_facebook_page_id = fields.Char(related="partner_id.facebook_page_id")
    partner_instagram_page_id = fields.Char(related="partner_id.instagram_page_id")
    partner_tiktok_access_token = fields.Char(related="partner_id.tiktok_access_token")

    partner_id_facebook_ad_account = fields.Char(related="partner_id.id_facebook_ad_account")

    facebook_ad_campaigns_ids = fields.One2many(
        'facebook.ad.campaigns',
        'project_id',
        string='Campañas de Facebook'
    )

    def fetch_facebook_campaigns(self):
        # Eliminar todos los registros existentes en el modelo
        self.env['facebook.ad.campaigns'].sudo().search([]).unlink()
        access_token = self.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_key')
        # Get dates (assuming self.date_start and self.date are date/datetime objects)
        since_date = self.date_start
        until_date = self.date

        if not access_token:
            return

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
            existing = Campaign.search([('campaign_id', '=', c['id'])], limit=1)
            if existing:
                if existing.name != c['name']:
                    existing.write({'name': c['name']})
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

    @api.model_create_multi
    def create(self, vals_list):
        # Handle both single create and multi-create cases
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            partner_id = vals.get('partner_id')
            project_type = vals.get('project_type')

            if partner_id and project_type:
                existing_project = self.search([
                    ('partner_id', '=', partner_id),
                    ('project_type', '=', project_type)
                ], limit=1)
                if existing_project:
                    raise ValidationError(
                        "Ya existe un proyecto para este cliente con el mismo tipo de proyecto.")

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
                raise ValidationError(
                    "Ya existe otro proyecto con este cliente y tipo de proyecto."
                )

        return super(project_project, self).write(vals)

    def get_facebook_data(self, since, until):
        BASE_URL = f"https://graph.facebook.com/v22.0/{self.partner_facebook_page_id}/insights?"

        metrics = [
            'page_impressions',
            'page_views_total',
            'page_fans',
            'page_fan_adds',
            'page_fan_removes',
            'page_impressions_unique',
            'page_post_engagements',
            'page_posts_impressions',
            'post_reactions_like_total'
        ]

        params = {
            'metric': ','.join(metrics),
            'since': since,
            'until': until,
            'period': 'day',
            'access_token': self.partner_page_access_token,
        }

        all_data = []
        url = BASE_URL

        try:
            while url:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                result = response.json()

                data = result.get('data', [])
                all_data.extend(data)

                url = result.get('paging', {}).get('next')
                params = {}  # Los parámetros ya están en la URL del "next"

            totals = {}
            for metric in all_data:
                name = metric['name']
                values = metric.get('values', [])
                if name in ['page_fans']:
                    totals[name] = values[-1]['value'] if values else 0
                else:
                    total_value = sum(
                        entry['value'] for entry in values if isinstance(entry['value'], (int, float)))
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
            resumen_por_tipo = {
                ptype: {
                    'posts': data['posts'],
                    'reach': data['reach'],
                    'reactions': data['reactions'],
                    'comments': data['comments'],
                    'shares': data['shares'],
                }
                for ptype, data in post_type_data.items()
            }

            top_5_posts = sorted(posts_matrix, key=lambda x: x['reach'], reverse=True)[:3]

            return {
                'totals': totals,
                'post_type_summary': resumen_por_tipo,
                'top_posts': top_5_posts,
            }

        except requests.exceptions.RequestException as e:
            raise ValidationError(f"Error al conectar con Facebook: {str(e)}")

    def get_instagram_data(self, since, until):
        # 1) Métricas básicas
        account_metrics = requests.get(
            f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}",
            params={
                'access_token': self.partner_page_access_token,
                'fields': 'followers_count,media_count'
            },
            timeout=15
        ).json()

        # Inicializar métricas
        metrics = {
            'reach': 0, 'profile_views': 0, 'accounts_engaged': 0,
            'total_interactions': 0, 'likes': 0, 'comments': 0,
            'shares': 0, 'saves': 0, 'replies': 0,
            'follows_and_unfollows': 0, 'views': 0
        }

        # 2) Request inicial de insights con parámetros
        base_url = f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}/insights"
        params = {
            'access_token': self.partner_page_access_token,
            'metric': ','.join(metrics.keys()),
            'period': 'day',
            'metric_type': 'total_value',
            'since': since,
            'until': until
        }

        response = requests.get(base_url, params=params, timeout=15).json()
        url = response.get('paging', {}).get('next')
        data_pages = [response]

        # 3) Paginación
        while url:
            response = requests.get(url, timeout=15).json()
            data_pages.append(response)
            url = response.get('paging', {}).get('next')

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
        media_url = f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}/media"
        media_params = {
            'access_token': self.partner_page_access_token,
            'fields': (
                'id,media_type,permalink,media_url,thumbnail_url,caption,timestamp,'
                'insights.metric('
                'impressions,reach,total_interactions,likes,comments,shares,'
                'saved,video_views,plays'
                ').period(day)'
            ),
            'since': since,
            'until': until,
            'limit': 100,
        }

        all_media = []
        next_url, params = media_url, media_params
        while next_url:
            resp = requests.get(next_url, params=params, timeout=15).json()
            all_media.extend(resp.get('data', []))
            next_url = resp.get('paging', {}).get('next')
            params = None

        types = ['IMAGE', 'VIDEO', 'CAROUSEL']
        summary = {
            t: {
                'impressions': 0,
                'reach': 0,
                'total_interactions': 0,
                'likes': 0,
                'comments': 0,
                'shares': 0,
                'saved': 0,
                'video_views': 0,
                'plays': 0,
            }
            for t in types
        }

        for post in all_media:
            mtype = post.get('media_type')
            insights = post.get('insights', {}).get('data', [])
            ins = {i['name']: i['values'][0]['value'] for i in insights}
            if mtype in summary:
                for metric in summary[mtype].keys():
                    summary[mtype][metric] += ins.get(metric, 0)

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
            })
        top_posts = sorted(posts_with_reach, key=lambda x: x['reach'], reverse=True)[:5]

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
            try:
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


            except Exception as e:
                raise ValidationError(f"Error al obtener imagen del anuncio: {e}")
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
                    action_value = action.get('value', 0)
                    campaign_data['actions'][action_type] = action_value

                all_campaigns_data.append(campaign_data)

            except requests.exceptions.RequestException:
                continue
            except Exception:
                continue

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
                'cost_per_conversion': round(avg_cost_per_conversion, 2),
            },
            'campaigns': all_campaigns_data,
        }

    def action_generate_report(self):
        self.ensure_one()

        # Verificación de configuraciones mínimas
        if not (self.partner_facebook_page_id or self.partner_instagram_page_id):
            raise ValidationError("Debe configurar al menos una cuenta de Facebook o Instagram.")

        # Definir rangos de fechas como timestamps
        since = int(time.mktime(self.date_start.timetuple()))
        until = int(time.mktime(self.date.timetuple()))
        facebook_data = {}
        instagram_data = {}
        meta_ads_data = {}

        if self.partner_facebook_page_id:
            facebook_data = self.get_facebook_data(since, until)
            meta_ads_data = self.get_meta_ads_data(since, until)

        if self.partner_instagram_page_id:
             instagram_data = self.get_instagram_data(since, until)

        data = {
            'facebook_data': facebook_data,
            'instagram_data': instagram_data,
            'meta_ads_data': meta_ads_data,
            'report_period': {
                'since': self.date_start.strftime('%Y-%m-%d'),
                'until': self.date.strftime('%Y-%m-%d'),
            },
            'partner_name': self.partner_id.name,
        }
        # print("📄 DATOS DEL REPORTE DE MARKETING:")
        #print(json.dumps(data, indent=4, ensure_ascii=False))

        # Generar y devolver el reporte en PDF
        return self.env.ref('gl_geniolibre.gl_print_marketing_report').report_action(self, data={'data': data})


def action_print_report(self):
    data = {...}  # Tu diccionario de datos
    return {
        'type': 'ir.actions.report',
        'report_name': 'gl_geniolibre.gl_print_marketing_report_template',
        'report_type': 'qweb-pdf',
        'data': {'data': data},  # Pasar datos en clave 'data'
        'config': False
    }
