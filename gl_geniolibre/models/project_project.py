# -*- coding: utf-8 -*-:
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
        print(params)
        response = requests.get(url, params=params)
        response.raise_for_status()
        campaigns = response.json().get('data', [])
        print(campaigns)
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

    def create_marketing_report(self):
        # Get dates (assuming self.date_start and self.date are date/datetime objects)
        since_date = self.date_start
        until_date = self.date

        # Convert to Unix timestamps (integers)
        since = int(time.mktime(since_date.timetuple()))
        until = int(time.mktime(until_date.timetuple()))

        def get_facebook_data():
            BASE_URL = f"https://graph.facebook.com/v22.0/{self.partner_facebook_page_id}/insights?"
            # 2. Métricas generales de la página
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
                # === OBTENER INSIGHTS ===
                while url:
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    result = response.json()

                    data = result.get('data', [])
                    all_data.extend(data)

                    url = result.get('paging', {}).get('next')
                    params = {}  # ya están en la URL del "next"

                # Procesar totales
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

                print("Totales:")
                for metric_name, total_value in totals.items():
                    print(f"{metric_name}: {total_value}")

                # === TOP 5 CIUDADES ===
                # city_url = f"https://graph.facebook.com/v22.0/{self.partner_facebook_page_id}/insights/page_fans_city"
                # city_params = {
                #     'access_token': self.partner_page_access_token
                # }
                # city_response = requests.get(city_url, params=city_params, timeout=10)
                # city_response.raise_for_status()
                # city_data = city_response.json()
                #
                # city_likes = {}
                # if city_data.get('data') and city_data['data'][0].get('values'):
                #     city_likes = city_data['data'][0]['values'][0]['value']
                #
                # top_cities = sorted(city_likes.items(), key=lambda x: x[1], reverse=True)[:5]
                #
                # print("\nTop 5 Ciudades con más Me Gusta:")
                # for city, likes in top_cities:
                #     print(f"{city}: {likes}")

                # === RENDIMIENTO POR TIPO DE PUBLICACIÓN ===
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
                    'fields': 'id,shares,attachments,created_time,full_picture,comments.metric(total_count),insights.metric(post_impressions,post_impressions_organic,post_impressions_paid,post_reactions_by_type_total),is_published',
                    'since': since,
                    'until': until,
                    'access_token': self.partner_page_access_token,
                }

                while post_url:
                    post_response = requests.get(post_url, params=post_params, timeout=15)
                    post_result = post_response.json()
                    posts = post_result.get('data', [])
                    posts_matrix = []

                    for post in posts:
                        attachments = post.get('attachments', {}).get('data', [{}])[0]
                        post_type = attachments.get('type', 'post').lower()
                        insights = post.get('insights', {}).get('data', [])
                        comments = post.get('comments', {}).get('data', [])

                        # Convertir insights a diccionario para fácil acceso
                        insights_dict = {item['name']: item['values'][0]['value'] for item in insights}

                        # Convertir comments a diccionario para fácil acceso
                        comments_dict = {item['name']: item['values'][0]['value'] for item in comments}

                        reach = insights_dict.get('post_impressions', 0)
                        organic_reach = insights_dict.get('post_impressions_organic', 0)
                        paid_reach = insights_dict.get('post_impressions_paid', 0)

                        # Extraer shares
                        shares_data = post.get('shares', {})
                        total_shares = shares_data.get('count', 0) if isinstance(shares_data, dict) else 0

                        # Extraer comentarios
                        comments_data = post.get('comments', {}).get('summary', {})
                        total_comments = comments_data.get('total_count', 0)

                        reactions_by_type = insights_dict.get('post_reactions_by_type_total', {})
                        total_reactions = sum(reactions_by_type.values()) if isinstance(reactions_by_type, dict) else 0

                        picture_url = post.get('full_picture', '')
                        created_time = post.get('created_time', '')
                        post_id = post.get('id', '')

                        posts_matrix.append({
                            'type': post_type,
                            'reach': reach,
                            'organic_reach': organic_reach,
                            'paid_reach': paid_reach,
                            'reactions': total_reactions,
                            'reactions_by_type': reactions_by_type,
                            'picture_url': picture_url,
                            'created_time': created_time,
                            'post_id': post_id,
                            'comments': total_comments,
                            'shares': total_shares,
                        })

                        # if picture_url:
                        #     post_type_data[post_type]['pictures'].append(picture_url)

                        post_type_data[post_type]['posts'] += 1
                        post_type_data[post_type]['reach'] += reach
                        post_type_data[post_type]['reactions'] += total_reactions
                        post_type_data[post_type]['comments'] += total_comments
                        post_type_data[post_type]['shares'] += total_shares

                    post_url = post_result.get('paging', {}).get('next', '')
                    post_params = {}

                # === Mostrar resultados sin tabla, solo líneas ===
                print("\nRendimiento por tipo de publicación:")
                print("Tipo - Posts - Reach - Reactions - Comentarios - Shares")
                for ptype, metrics in sorted(post_type_data.items(), key=lambda x: x[1]['posts'], reverse=True):
                    print(
                        f"{ptype.capitalize()} - {metrics['posts']} - {metrics['reach']} - {metrics['reactions']} - "
                        f"{metrics['comments']} - {metrics['shares']}"
                    )

                # Ordenar y seleccionar solo los 5 primeros
                posts_matrix_sorted = sorted(posts_matrix, key=lambda x: x['reach'], reverse=True)[:5]

                # Mostrar los resultados ordenados
                print("\nTop 5 posts ordenados por alcance:")
                print("-" * 180)
                print(
                    f"{'Tipo':<10} | {'Fecha':<20} | {'Reach':<10} | {'Orgánico':<10} | {'Pago':<10} | "
                    f"{'Reacciones':<12} | {'Comentarios':<12} | {'Shares':<12} | {'URL Imagen'}"
                )
                print("-" * 180)

                for post in posts_matrix_sorted:
                    print(
                        f"{post['type'].capitalize():<10} | "
                        f"{post['created_time'][:19]:<20} | "
                        f"{post['reach']:<10} | "
                        f"{post['organic_reach']:<10} | "
                        f"{post['paid_reach']:<10} | "
                        f"{post['reactions']:<12} | "
                        f"{post['comments']:<12} | "
                        f"{post['shares']:<12} | "
                        f"{post['picture_url']}"
                    )
                    print("  Desglose de reacciones:")
                    for reaction_type, count in post.get('reactions_by_type', {}).items():
                        print(f"    {reaction_type.capitalize()}: {count}")




            except requests.exceptions.RequestException as e:
                raise ValidationError(f"Error al conectar con Facebook: {str(e)}")

        def get_instagram_data():
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
            # Hacemos la petición inicial
            response = requests.get(base_url, params=params, timeout=15).json()

            # Extraemos datos y preparamos siguiente URL de paginación
            url = response.get('paging', {}).get('next')
            data_pages = [response]  # guardamos la primera página

            # 3) Mientras haya paginación, ir pidiendo sólo la URL next
            while url:
                response = requests.get(url, timeout=15).json()
                data_pages.append(response)
                url = response.get('paging', {}).get('next')

            # 4) Iterar sobre todas las páginas
            for page in data_pages:
                for metric in page.get('data', []):
                    name = metric.get('name')
                    if name in metrics:
                        # total_value puede venir directo o anidado, según API
                        val = metric.get('values') or metric.get('total_value', {})
                        # en v22.0 el formato suele ser metric['values'] = [{'value': X, 'end_time':...}, ...]
                        if isinstance(val, list):
                            for entry in val:
                                metrics[name] += entry.get('value', 0)
                        else:
                            metrics[name] += val.get('value', 0)

            # 5) Mostrar resultados
            print("Métricas totales:")
            print('Seguidores', account_metrics.get('followers_count'))
            for k, v in metrics.items():
                print(f"{k.capitalize()}: {v}")

            # === Estadísticas por tipo de publicación ===
            # === 1) Traer lista de medios con sus insights diarios ===
            media_url = f"https://graph.facebook.com/v22.0/{self.partner_instagram_page_id}/media"
            media_params = {
                'access_token': self.partner_page_access_token,
                'fields': (
                    'id,media_type,permalink,caption,timestamp,'
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
                params = None  # sólo en la primera petición

            # === 2) Acumular totales por tipo de publicación ===
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
                # Verificación de métricas y muestra de datos crudos para debug
                print(f"Post ID: {post.get('id')} - Insights: {ins}")  # Datos crudos para verificación
                if mtype in summary:
                    for metric in summary[mtype].keys():
                        summary[mtype][metric] += ins.get(metric, 0)

            # === 3) Construir y ordenar Top 5 posts por alcance ===
            posts_with_reach = []
            for post in all_media:
                insights = post.get('insights', {}).get('data', [])
                ins = {i['name']: i['values'][0]['value'] for i in insights}
                posts_with_reach.append({
                    'id': post.get('id'),
                    'media_type': post.get('media_type'),
                    'permalink': post.get('permalink'),
                    'caption': post.get('caption', ''),
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

            # === 4) Imprimir resultados ===

            # Resumen por tipo
            print("Rendimiento por tipo de publicación:")
            print("Tipo       - Posts - Reach - Reactions - Comentarios - Shares - Saves")
            for mtype, metrics in summary.items():
                count = sum(1 for p in all_media if p.get('media_type') == mtype)
                reach = metrics['reach']
                reactions = metrics['total_interactions']
                comments = metrics['comments']
                shares = metrics['shares']
                saves = metrics['saved']
                print(
                    f"{mtype.ljust(10)} - "
                    f"{str(count).rjust(5)} - "
                    f"{str(reach).rjust(5)} - "
                    f"{str(reactions).rjust(9)} - "
                    f"{str(comments).rjust(11)} - "
                    f"{str(shares).rjust(6)} - "
                    f"{str(saves).rjust(5)}"
                )

            # Top 5 posts
            print("\nTop 5 posts ordenados por alcance:")
            print("-" * 150)
            print(
                "Tipo       | Fecha                | Reach     | Reacciones  | Likes | Comentarios  | Shares       | Saves        | URL Imagen"
            )
            print("-" * 150)
            for post in top_posts:
                print(
                    f"{post['media_type'].ljust(10)} | "
                    f"{post['created_at'].ljust(20)} | "
                    f"{str(post['reach']).rjust(10)} | "
                    f"{str(post['total_interactions']).rjust(12)} | "
                    f"{str(post['likes']).rjust(12)} | "
                    f"{str(post['comments']).rjust(12)} | "
                    f"{str(post['shares']).rjust(12)} | "
                    f"{str(post['saved']).rjust(12)} | "
                    f"{post['permalink']}"
                )

        def get_meta_ads_data():
            self.ensure_one()

            if not self.partner_page_access_token:
                raise ValidationError("No hay Access Token configurado para esta página.")

                # ⚡ Aquí validamos que haya campañas seleccionadas
            if not self.facebook_ad_campaigns_ids or len(self.facebook_ad_campaigns_ids) == 0:
                raise ValidationError("Debe seleccionar al menos una campaña de Facebook para continuar.")

            print("=== Obteniendo métricas para las campañas seleccionadas ===")

            for campaign in self.facebook_ad_campaigns_ids:
                if not campaign.campaign_id:
                    print(f"La campaña {campaign.name} no tiene ID de Facebook configurado.")
                    continue

                url = f"https://graph.facebook.com/v22.0/{campaign.campaign_id}"
                params = {
                    'access_token': self.partner_page_access_token,
                    'fields': 'id,name,status,effective_status,insights{impressions,clicks,spend,reach}',
                    'since': self.date_start,  # Fecha de inicio
                    'until': self.date,  # Fecha de fin
                }
                #agrgar actions, conversions

                try:
                    response = requests.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    print(data)
                    campaign_data = {
                        'campaign_id': data.get('id', ''),
                        'name': data.get('name', ''),
                        'status': data.get('status', ''),
                        'effective_status': data.get('effective_status', ''),
                        'impressions': 0,
                        'clicks': 0,
                        'spend': 0,
                        'reach': 0,
                    }

                    insights = data.get('insights', {}).get('data', [{}])[0]
                    if insights:
                        campaign_data.update({
                            'impressions': insights.get('impressions', 0),
                            'clicks': insights.get('clicks', 0),
                            'spend': insights.get('spend', 0),
                            'reach': insights.get('reach', 0),
                        })

                    # Imprimimos la información
                    print(f"--- Campaña: {campaign_data['name']} ---")
                    print(f"ID: {campaign_data['campaign_id']}")
                    print(f"Estado: {campaign_data['status']}")
                    print(f"Estado Efectivo: {campaign_data['effective_status']}")
                    print(f"Impresiones: {campaign_data['impressions']}")
                    print(f"Clicks: {campaign_data['clicks']}")
                    print(f"Gasto: {campaign_data['spend']}")
                    print(f"Alcance: {campaign_data['reach']}")
                    print("-" * 40)

                except requests.exceptions.RequestException as e:
                    return ValidationError(f"Error al conectar con la API de Facebook: {str(e)}")
                except Exception as e:
                    return ValidationError(f"Error al obtener datos de campañas de Facebook: {str(e)}")



        if self.partner_facebook_page_id:
            print("get_facebook_data")
            #get_facebook_data()
            print("get_meta_ads_data")
            get_meta_ads_data()
        else:
            raise ValidationError(
                "No se configuró el ID de la Página de Facebook")

        if self.partner_instagram_page_id:
            print("get_instagram_data")
            #get_instagram_data()
