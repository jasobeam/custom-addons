# -*- coding: utf-8 -*-:
import datetime, time, pytz, requests

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from urllib.parse import urlparse, parse_qs
from collections import defaultdict
from datetime import datetime
from google.ads.googleads.client import GoogleAdsClient

API_VERSION = "v23.0"

class GoogleAdCampaign(models.Model):
    _name = 'google.ad.campaigns'
    _description = 'Google Ad Campaigns'
    _sql_constraints = [
        ('campaign_id_unique', 'unique(campaign_id)', 'La campaña ya existe.'),
    ]

    name = fields.Char('Nombre')
    campaign_id = fields.Char('ID de Campaña', required=True)
    account_id = fields.Char('ID Cuenta Google Ads')
    project_id = fields.Many2one('project.project', string='Proyecto')

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

    post_progress = fields.Char(string="Posts Publicados", compute="_compute_publication_counts", store=False)
    historia_progress = fields.Char(string="Historias Publicadas", compute="_compute_publication_counts", store=False)
    reel_progress = fields.Char(string="Reels Publicados", compute="_compute_publication_counts", store=False)

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

    partner_id_google_ads_account = fields.Char(related="partner_id.id_google_ads_account")
    google_ad_campaigns_ids = fields.One2many('google.ad.campaigns', 'project_id', string='Campañas de Google Ads')

    @api.depends('task_ids.post_estado', 'task_ids.tipo', 'partner_plan_post', 'partner_plan_historia', 'partner_plan_reel')
    def _compute_publication_counts(self):  # optimizado
        for project in self:
            # Usar el ORM de Odoo para calcular cantidades directamente en la búsqueda
            tasks_data = self.env['project.task'].read_group(domain=[
                ('project_id', '=', project.id)
            ], fields=[
                'tipo'
            ], groupby=[
                'tipo'
            ])

            # Inicializar contadores a 0
            post_count = 0
            historia_count = 0
            reel_count = 0

            # Mapear resultados del read_group
            for data in tasks_data:
                tipo = data['tipo']
                count = data['tipo_count']
                if tipo == 'feed':
                    post_count = count
                elif tipo == 'video_stories':
                    historia_count = count
                elif tipo == 'video_reels':
                    reel_count = count

            # Actualizar campos de progreso utilizando los valores calculados
            project.post_progress = f"{post_count} de {project.partner_plan_post or 0} posts"
            project.historia_progress = f"{historia_count} de {project.partner_plan_historia or 0} historias"
            project.reel_progress = f"{reel_count} de {project.partner_plan_reel or 0} reels"

    @api.model_create_multi
    def create(self, vals_list):  # optimizado
        """
        Validar duplicados de 'partner_id' y 'project_type' para evitar la creación de proyectos repetidos.
        """
        for vals in vals_list:
            partner_id = vals.get('partner_id')
            project_type = vals.get('project_type')

            # Comprobamos si ya existe un proyecto para este cliente y tipo
            if partner_id and project_type:
                existing_project = self.sudo().search([
                    ('partner_id', '=', partner_id),
                    ('project_type', '=', project_type)
                ], limit=1)

                if existing_project:
                    partner_name = self.env['res.partner'].browse(partner_id).name
                    project_type_label = dict(
                        self.fields_get()['project_type']['selection']).get(project_type, project_type)
                    raise ValidationError(f"Ya existe un proyecto para el cliente '{partner_name}' con el tipo '{project_type_label}'.")

        # Creamos los registros utilizando la lógica estándar
        return super(project_project, self).create(vals_list)

    def write(self, vals):  # optimizado
        """
        Validar que no existan duplicados de tipo de proyecto y cliente al actualizar registros.
        """
        # Obtener nuevos valores asignados o valores actuales del registro
        partner_id = vals.get('partner_id')
        project_type = vals.get('project_type')

        # Si no hay cambios relevantes, continúa
        if not partner_id and not project_type:
            return super(project_project, self).write(vals)

        for record in self:
            # Asignar valores "actuales" en caso de no estar en 'vals'
            if record.date_start and record.date:
                if (record.date - record.date_start).days > 30:
                    raise ValidationError("El rango entre fechas no puede ser mayor a 30 días.")

            updated_partner_id = partner_id or record.partner_id.id
            updated_project_type = project_type or record.project_type

            # Buscar proyectos existentes que coincidan con las condiciones
            duplicate_project = self.sudo().search([
                ('id', '!=', record.id),  # Evitar comparar con el mismo registro
                ('partner_id', '=', updated_partner_id),
                ('project_type', '=', updated_project_type)
            ], limit=1)

            if duplicate_project:
                partner_name = self.env['res.partner'].browse(updated_partner_id).name
                project_type_label = dict(
                    self.fields_get()['project_type']['selection']).get(updated_project_type, updated_project_type)
                raise ValidationError(f"Otro proyecto del cliente '{partner_name}' con el tipo '{project_type_label}' ya existe.")

        # Aplicar la escritura de los valores
        return super(project_project, self).write(vals)

    def fetch_facebook_campaigns(self):  # Optimizado
        # Validar token de acceso
        access_token = self.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_key')
        if not access_token:
            raise ValidationError("No existe un token válido")

        # Validar fechas y asegurar que sean del tipo correcto (date)
        since_date = self.date_start if isinstance(self.date_start, fields.Date) else self.date_start
        until_date = self.date if isinstance(self.date, fields.Date) else self.date

        if isinstance(since_date, datetime):
            since_date = since_date.date()
        if isinstance(until_date, datetime):
            until_date = until_date.date()

        # Realizar consulta API para campañas activas
        url = f"https://graph.facebook.com/{API_VERSION}/act_{self.partner_id_facebook_ad_account}/campaigns"
        params = {
            'access_token': access_token,
            'fields': 'name,id,start_time,stop_time',
            'effective_status': '["ACTIVE"]',
            'limit': 1000,
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            error = response.json().get('error', {}).get('message', 'Error desconocido')
            raise ValidationError(f"Error al obtener campañas: {error}")

        campaigns = response.json().get('data', [])
        if not campaigns:
            return

        # Filtrar campañas activas dentro del rango de fechas
        filtered_campaigns = [camp for camp in campaigns if
                              self._is_campaign_within_range(camp, since_date, until_date)]

        # Registrar o actualizar campañas en Odoo
        CampaignModel = self.env['facebook.ad.campaigns'].sudo()
        existing_campaign_ids = CampaignModel.search_read([
            ('account_id', '=', self.partner_id_facebook_ad_account)
        ], [
            'campaign_id'
        ])
        existing_campaign_ids = {rec['campaign_id'] for rec in existing_campaign_ids}

        new_campaign_ids = set()
        for campaign in filtered_campaigns:
            campaign_id = campaign['id']
            new_campaign_ids.add(campaign_id)

            # Actualizar si existe, sino crear nuevo
            existing_campaign = CampaignModel.search([
                ('campaign_id', '=', campaign_id)
            ], limit=1)
            if existing_campaign:
                existing_campaign.write({
                    'name': campaign['name']
                })
            else:
                CampaignModel.create({
                    'name': campaign['name'],
                    'campaign_id': campaign_id,
                    'account_id': self.partner_id_facebook_ad_account,
                })

        # Eliminar campañas obsoletas
        to_remove = existing_campaign_ids.difference(new_campaign_ids)
        if to_remove:
            CampaignModel.search([
                ('account_id', '=', self.partner_id_facebook_ad_account),
                ('campaign_id', 'in', list(to_remove)),
            ]).unlink()

    def _is_campaign_within_range(self, campaign, since_date, until_date):  # optimizado
        """Valida que la campaña esté dentro del rango de fechas."""
        start_str = campaign.get('start_time')
        end_str = campaign.get('stop_time')
        start_date = fields.Date.from_string(start_str) if start_str else None
        end_date = fields.Date.from_string(end_str) if end_str else None

        # Verificar superposición
        return ((start_date is None or start_date <= until_date) and (end_date is None or end_date >= since_date))

    def fetch_google_campaigns(self):  # Optimizado
        # Obtener configuración técnica
        cfg = self.env['ir.config_parameter'].sudo()
        credenciales = {
            'developer_token': cfg.get_param('gl_google.developer_token'),
            'client_id': cfg.get_param('gl_google.client_id'),
            'client_secret': cfg.get_param('gl_google.client_secret'),
            'refresh_token': cfg.get_param('gl_google.refresh_token'),
            'login_customer_id': cfg.get_param('gl_google.login_customer_id'),
        }

        # Validar que todas las credenciales existan
        if not all(credenciales.values()):
            missing_creds = ", ".join([k for k, v in credenciales.items() if not v])
            raise ValidationError(f"Faltan las siguientes credenciales en la configuración técnica: {missing_creds}")

        CampaignGA = self.env['google.ad.campaigns'].sudo()

        for record in self:
            # Validar cuenta de Google Ads
            account = record.partner_id_google_ads_account
            if not account:
                raise ValidationError("El proyecto no tiene una cuenta de Google Ads asignada.")

            # Validar fechas del proyecto
            since_date = record.date_start
            until_date = record.date
            if not since_date or not until_date:
                raise ValidationError("Por favor define las fechas de inicio y fin del proyecto.")

            # Configurar cliente de Google Ads
            client = GoogleAdsClient.load_from_dict({
                **credenciales,
                'use_proto_plus': True,
            })
            service = client.get_service('GoogleAdsService')

            # Limpiar campañas previas asociadas a esta cuenta
            existing_campaigns = CampaignGA.search([
                ('account_id', '=', account)
            ])
            existing_campaigns.unlink()

            # Formatear fechas en 'YYYY-MM-DD'
            since_str, until_str = since_date.strftime('%Y-%m-%d'), until_date.strftime('%Y-%m-%d')

            # Definir query para campañas con impresiones
            query = f"""
                SELECT campaign.id, campaign.name, campaign.status, metrics.impressions
                FROM campaign
                WHERE segments.date BETWEEN '{since_str}' AND '{until_str}'
                  AND metrics.impressions > 0
            """

            # Ejecutar query y procesar respuesta
            response = service.search(customer_id=account, query=query)
            api_ids = [str(row.campaign.id) for row in response]

            # Crear campañas
            for row in response:
                CampaignGA.create({
                    'campaign_id': str(row.campaign.id),
                    'name': row.campaign.name,
                    'account_id': account,
                    'project_id': record.id,
                })

            # Eliminar campañas obsoletas
            CampaignGA.search([
                ('account_id', '=', account),
                ('campaign_id', 'not in', api_ids),
            ]).unlink()

    def get_facebook_data(self, since, until):#Optimizado
        BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{self.partner_facebook_page_id}"

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
        url = f"{BASE_URL}/insights"
        original_since, original_until = int(since), int(until)
        while url:
            try:
                response = requests.get(url, params=params if '?' not in url else {}, timeout=10)
                response.raise_for_status()
                result = response.json()

            except requests.exceptions.RequestException as e:
                raise ValidationError(f"Error fetching insights data: {e}")


            all_data.extend(result.get('data', []))
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

        # Calcular totales
        totals = {}
        for metric in all_data:
            name = metric['name']
            values = metric.get('values', [])
            if name == 'page_fans':
                totals[name] = values[-1]['value'] if values else 0
            else:
                totals[name] = sum(entry['value'] for entry in values if isinstance(entry['value'], (int, float)))
        # Procesar publicaciones
        post_url = f"{BASE_URL}/feed"
        post_params = {
            'fields': 'id,message,shares,attachments,created_time,full_picture,comments.metric(total_count),'
                      'insights.metric(post_impressions,post_impressions_organic,post_impressions_paid,post_reactions_by_type_total),'
                      'is_published',
            'since': since,
            'until': until,
            'access_token': self.partner_page_access_token,
        }
        posts_matrix = []
        post_type_data = defaultdict(lambda: {
            'posts': 0,
            'reach': 0,
            'organic_reach': 0,
            'paid_reach': 0,
            'reactions': 0,
            'comments': 0,
            'shares': 0
        })

        # 3. Bucle principal de paginación
        page_count = 0
        max_pages = 50  # Límite de páginas para evitar bucles infinitos

        while post_url and page_count < max_pages:
            try:
                # 4. Obtener datos de la API
                post_response = requests.get(post_url, params=post_params, timeout=15)
                post_response.raise_for_status()
                post_result = post_response.json()

                # 5. Debug: Mostrar respuesta cruda

                # 6. Procesar cada post
                posts = post_result.get('data', [])
                for post in posts:
                    try:
                        # 7. Extraer datos básicos del post
                        attachments = post.get('attachments', {}).get('data', [
                            {}
                        ])
                        post_type = attachments[0].get('type', 'post').lower() if attachments else 'post'

                        # 8. Procesar insights
                        insights = post.get('insights', {}).get('data', [])
                        insights_dict = {}
                        for item in insights:
                            try:
                                insights_dict[item['name']] = item['values'][0]['value']
                            except (KeyError, IndexError, TypeError):
                                raise ValidationError(KeyError, IndexError, TypeError)

                        # 9. Calcular métricas
                        reach = insights_dict.get('post_impressions', 0)
                        organic_reach = insights_dict.get('post_impressions_organic', 0)
                        paid_reach = insights_dict.get('post_impressions_paid', 0)

                        shares_data = post.get('shares', {})
                        total_shares = shares_data.get('count', 0) if isinstance(shares_data, dict) else 0

                        comments_data = post.get('comments', {}).get('summary', {})
                        total_comments = comments_data.get('total_count', 0)

                        reactions_by_type = insights_dict.get('post_reactions_by_type_total', {})
                        total_reactions = sum(reactions_by_type.values()) if isinstance(reactions_by_type, dict) else 0

                        # 10. Construir objeto del post
                        post_data = {
                            'type': post_type,
                            'reach': reach,
                            'organic_reach': organic_reach,
                            'paid_reach': paid_reach,
                            'reactions': total_reactions,
                            'reactions_by_type': reactions_by_type,
                            'picture_url': post.get('full_picture', ''),
                            'message': (post.get('message', '') or '')[:50],
                            'created_time': post.get('created_time', ''),
                            'post_id': post.get('id', ''),
                            'comments': total_comments,
                            'shares': total_shares,
                        }

                        print(post_data["message"])
                        posts_matrix.append(post_data)

                        # 11. Actualizar estadísticas por tipo
                        post_type_data[post_type]['posts'] += 1
                        post_type_data[post_type]['reach'] += reach
                        post_type_data[post_type]['reactions'] += total_reactions
                        post_type_data[post_type]['comments'] += total_comments
                        post_type_data[post_type]['shares'] += total_shares
                    except Exception as post_error:
                        raise ValidationError(Exception)

                # 12. Preparar siguiente página
                post_url = post_result.get('paging', {}).get('next')
                post_params = {}  # Los parámetros ya vienen en la URL 'next'
                page_count += 1

            except requests.exceptions.RequestException as e:
                raise ValidationError(f"Error de conexión: {str(e)}")
            except Exception as e:
                raise ValidationError(f"Error inesperado: {str(e)}")

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

    def get_instagram_data(self, since, until):#Optimizado
        # 1) Métricas básicas
        original_since, original_until = int(since), int(until)
        account_metrics = requests.get(f"https://graph.facebook.com/{API_VERSION}/{self.partner_instagram_page_id}", params={
            'access_token': self.partner_page_access_token,
            'fields': 'followers_count,media_count'
        }, timeout=15).json()

        # Inicializar métricas
        metrics = dict.fromkeys([
            'reach',
            'profile_views',
            'accounts_engaged',
            'total_interactions',
            'likes',
            'comments',
            'shares',
            'saves',
            'replies',
            'follows_and_unfollows',
            'views',
            'profile_links_taps'
        ], 0)

        # 2) Request inicial de insights
        base_url = f"https://graph.facebook.com/{API_VERSION}/{self.partner_instagram_page_id}/insights"
        params = {
            'access_token': self.partner_page_access_token,
            'metric': ','.join(metrics.keys()),
            'period': 'day',
            'metric_type': 'total_value',
            'since': since,
            'until': until
        }

        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        result = response.json()

        # Usar generador para iterar en las páginas, evitando listas innecesarias en memoria
        def paginate_results(initial_result):
            yield initial_result
            next_url = initial_result.get('paging', {}).get('next')
            while next_url:
                response = requests.get(next_url, timeout=15)
                response.raise_for_status()
                result = response.json()
                yield result
                next_url = result.get('paging', {}).get('next')

        # Sumar métricas directamente en bucle, evitando adicionales listas temporales.
        for page in paginate_results(result):
            for metric in page.get('data', []):
                name = metric.get('name')
                if name in metrics:
                    values = metric.get('values') or metric.get('total_value', {})
                    if isinstance(values, list):
                        metrics[name] += sum(entry.get('value', 0) for entry in values)
                    else:
                        metrics[name] += values.get('value', 0)

        # === Estadísticas por tipo de publicación ===
        media_url = f"https://graph.facebook.com/{API_VERSION}/{self.partner_instagram_page_id}/media"
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

        # Usar otra paginación para evitar redundancias
        def paginate_media(url, params):
            while url:
                response = requests.get(url, params, timeout=15)
                response.raise_for_status()
                result = response.json()
                yield result.get('data', [])
                url = result.get('paging', {}).get('next')
                params = {}  # Limpiamos params ya que el siguiente `next` viene completo en la URL

        types = [
            'IMAGE',
            'VIDEO',
            'CAROUSEL'
        ]
        summary = {t: dict.fromkeys([
            'views',
            'reach',
            'total_interactions',
            'likes',
            'comments',
            'shares',
            'saved',
            'video_views',
            'plays'
        ], 0) for t in types}

        posts_with_reach = []
        for data in paginate_media(media_url, media_params):
            for post in data:
                insights = {i['name']: i['values'][0]['value'] for i in post.get('insights', {}).get('data', [])}
                mtype = post.get('media_type')

                if mtype in summary:
                    for metric in summary[mtype]:
                        summary[mtype][metric] += insights.get(metric, 0)

                # Solo almacenar posts relevantes
                posts_with_reach.append({
                    'id': post.get('id'),
                    'media_type': post.get('media_type'),
                    'thumbnail_url': post.get('thumbnail_url'),
                    'permalink': post.get('permalink'),
                    'media_url': post.get('media_url'),
                    'caption': post.get('caption', '')[:50],
                    'created_at': post.get('timestamp'),
                    'reach': insights.get('reach', 0),
                    'impressions': insights.get('impressions', 0),
                    'total_interactions': insights.get('total_interactions', 0),
                    'likes': insights.get('likes', 0),
                    'comments': insights.get('comments', 0),
                    'shares': insights.get('shares', 0),
                    'saved': insights.get('saved', 0),
                    'video_views': insights.get('video_views', 0),
                    'plays': insights.get('plays', 0),
                    'views': insights.get('views', 0),
                })

        summary = {k: v for k, v in summary.items() if any(val != 0 for val in v.values())}
        top_posts = sorted(posts_with_reach, key=lambda x: x['reach'], reverse=True)[:3]

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
            ads_url = f"https://graph.facebook.com/{API_VERSION}/{campaign_id}/ads"
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

            creative_url = f"https://graph.facebook.com/{API_VERSION}/{creative_id}"
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

            url = f"https://graph.facebook.com/{API_VERSION}/{campaign.campaign_id}"
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

                    if action_type == 'onsite_conversion.messaging_conversation_started_7d':
                        total_conversaciones += int(action_value)

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
                'total_conversaciones': total_conversaciones,
            },
            'campaigns': all_campaigns_data,
        }

    def get_google_ads_data(self, since, until):#optimizado
        """Obtiene datos de Google Ads para los proyectos especificados."""
        cfg = self.env['ir.config_parameter'].sudo()
        required_credentials = [
            'gl_google.developer_token',
            'gl_google.client_id',
            'gl_google.client_secret',
            'gl_google.refresh_token',
            'gl_google.login_customer_id'
        ]

        # Obtener y validar credenciales
        credentials = {cred: cfg.get_param(cred) for cred in required_credentials}
        missing = [cred for cred, val in credentials.items() if not val]
        if missing:  # Solo mostramos un error si falta alguna credencial
            raise ValidationError(f"Faltan credenciales en la configuración técnica: {', '.join(missing)}")

        # Resultados generales
        results = {}

        for project in self:
            try:
                # Validar cuenta de Google Ads y fechas del proyecto
                account = project.partner_id_google_ads_account
                if not account:
                    raise ValidationError(f"El proyecto {project.name} no tiene una cuenta de Google Ads asignada.")

                since_date, until_date = project.date_start, project.date
                if not since_date or not until_date:
                    raise ValidationError(f"Define las fechas de inicio y fin para el proyecto {project.name}.")

                # Inicializar cliente de Google Ads
                client = GoogleAdsClient.load_from_dict({
                    'developer_token': credentials['gl_google.developer_token'],
                    'client_id': credentials['gl_google.client_id'],
                    'client_secret': credentials['gl_google.client_secret'],
                    'refresh_token': credentials['gl_google.refresh_token'],
                    'login_customer_id': credentials['gl_google.login_customer_id'],
                    'use_proto_plus': True,
                })
                service = client.get_service('GoogleAdsService')

                # Formatear fechas
                since_str, until_str = since_date.strftime('%Y-%m-%d'), until_date.strftime('%Y-%m-%d')

                # Obtener IDs de campañas
                campaign_ids = [str(c.campaign_id) for c in project.google_ad_campaigns_ids]
                if not campaign_ids:
                    continue

                # Consultar datos de campañas
                campaigns_filter = ', '.join(campaign_ids)
                campaign_query = f"""
                    SELECT
                      campaign.id,
                      campaign.name,
                      metrics.impressions,
                      metrics.clicks,
                      metrics.cost_micros,
                      metrics.ctr,
                      metrics.average_cpc,
                      metrics.conversions_from_interactions_rate,
                      metrics.interaction_rate,
                      metrics.all_conversions,
                      metrics.cost_per_all_conversions
                    FROM campaign
                    WHERE campaign.id IN ({campaigns_filter})
                      AND segments.date BETWEEN '{since_str}' AND '{until_str}'
                """

                # Procesar respuesta en un generador (sin listas acumulativas innecesarias)
                def fetch_campaign_data():
                    response = service.search(customer_id=account, query=campaign_query)
                    for row in response:
                        yield {
                            'id': str(row.campaign.id),
                            'name': row.campaign.name,
                            'impressions': row.metrics.impressions,
                            'clicks': row.metrics.clicks,
                            'cost': round(float(row.metrics.cost_micros or 0) / 1_000_000, 2),
                            'ctr': round(float(row.metrics.ctr or 0), 2),
                            'average_cpc': round(float(row.metrics.average_cpc or 0) / 1_000_000, 2),
                            'conversion_rate': round(100 * float(row.metrics.conversions_from_interactions_rate or 0), 2),
                            'all_conversions': float(row.metrics.all_conversions or 0),
                            'cost_per_all_conversions': round(float(row.metrics.cost_per_all_conversions or 0) / 1_000_000, 2),
                            'interaction_rate': round(float(row.metrics.interaction_rate or 0), 2),
                        }

                campaigns = list(fetch_campaign_data())

                # Consultar top palabras clave
                keyword_query = f"""
                    SELECT
                        ad_group_criterion.keyword.text,
                        metrics.impressions,
                        metrics.clicks,
                        metrics.cost_micros,
                        metrics.conversions,
                        metrics.average_cpc
                    FROM keyword_view
                    WHERE segments.date BETWEEN '{since_str}' AND '{until_str}'
                      AND ad_group_criterion.status = 'ENABLED'
                      AND campaign.id IN ({campaigns_filter})
                      AND ad_group_criterion.keyword.text != ''
                    ORDER BY metrics.clicks DESC
                    LIMIT 10
                """

                # Procesar palabras clave en un paso único
                def fetch_keywords_data():
                    response = service.search(customer_id=account, query=keyword_query)
                    for row in response:
                        keyword_text = row.ad_group_criterion.keyword.text
                        if not keyword_text:  # Solo procesar palabras clave válidas
                            continue

                        conversions = row.metrics.conversions or 0.0
                        cost = float(row.metrics.cost_micros or 0) / 1_000_000
                        yield {
                            'keyword': keyword_text,
                            'clicks': row.metrics.clicks,
                            'impressions': row.metrics.impressions,
                            'conversions': conversions,
                            'cost': round(cost, 2),
                            'cost_per_conversion': round(cost / conversions, 2) if conversions else 0.0,
                            'average_cpc': round(float(row.metrics.average_cpc or 0) / 1_000_000, 2),
                        }

                keywords_summary = list(fetch_keywords_data())

                # Calcular resumen general dinámico
                total_clicks = sum(c.get('clicks', 0) for c in campaigns)
                total_impressions = sum(c.get('impressions', 0) for c in campaigns)
                total_cost = sum(c.get('cost', 0) for c in campaigns)
                total_conversions = sum(c.get('all_conversions', 0) for c in campaigns)

                summary = {
                    'total_campaigns': len(campaigns),
                    'account_currency': 'USD',  # Cambiar si es necesario
                    'impressions': total_impressions,
                    'clicks': total_clicks,
                    'spend': round(total_cost, 2),
                    'ctr': round((total_clicks / total_impressions * 100), 2) if total_impressions else 0.0,
                    'cpc': round(total_cost / total_clicks, 2) if total_clicks else 0.0,
                    'conversions': total_conversions,
                    'cost_per_conversion': round(total_cost / total_conversions, 2) if total_conversions else 0.0,
                }

                # Guardar en resultados
                results = {
                    'summary': summary,
                    'campaigns': campaigns,
                    'keywords_summary': keywords_summary,
                }
            except Exception as e:
                # Registrar error pero continuar
                raise ValidationError(f"Error al obtener datos de Google Ads para el proyecto {project.name}: {str(e)}")

        return results

    def action_generate_report(self):#Optimizado
        self.ensure_one()

        data_sources = [
            {
                'name': 'Facebook',
                'check': self.partner_facebook_page_id and self.facebook_ad_campaigns_ids,
                'fetch_method': self.get_facebook_data,
                'data_key': 'facebook_data',
            },
            {
                'name': 'Meta Ads',
                'check': self.partner_facebook_page_id and self.facebook_ad_campaigns_ids,
                'fetch_method': self.get_meta_ads_data,
                'data_key': 'meta_ads_data',
            },
            {
                'name': 'Instagram',
                'check': self.partner_instagram_page_id and self.facebook_ad_campaigns_ids,
                'fetch_method': self.get_instagram_data,
                'data_key': 'instagram_data',
            },
            {
                'name': 'Google Ads',
                'check': self.partner_id.id_google_ads_account and self.google_ad_campaigns_ids,
                'fetch_method': self.get_google_ads_data,
                'data_key': 'google_ads_data',
            },
        ]

        data = {
            'facebook_data': {},
            'instagram_data': {},
            'meta_ads_data': {},
            'google_ads_data': {},
            'report_period': {
                'since': self.date_start.strftime('%Y-%m-%d'),
                'until': self.date.strftime('%Y-%m-%d'),
            },
            'partner_name': self.partner_id.name,
            'partner_id': self.partner_id.id,
        }

        messages = []
        has_errors = False

        try:
            if not (self.partner_facebook_page_id or self.partner_instagram_page_id):
                raise ValidationError("Debe configurar al menos una cuenta de Facebook o Instagram.")

            # Rango de fechas
            since = int(time.mktime(self.date_start.timetuple()))
            end_dt_utc = datetime.combine(self.date, datetime.max.time()).replace(tzinfo=pytz.UTC)
            until = int(end_dt_utc.timestamp())

            # Iterar sobre las fuentes de datos
            for source in data_sources:
                if not source['check']:
                    continue

                try:
                    # Obtener datos del método correspondiente
                    fetched_data = source['fetch_method'](since, until)
                    if fetched_data:
                        data[source['data_key']] = fetched_data
                        messages.append(f"✅ {source['name']}: datos obtenidos.")
                    else:
                        messages.append(f"⚠️ {source['name']}: sin datos en el período.")
                except Exception as e:
                    has_errors = True
                    messages.append(f"❌ {source['name']}: error - {str(e)}")

            # Validar si se producen errores durante el procesamiento
            if has_errors:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': "Reporte generado con advertencias",
                        'message': "\n\n".join([msg for msg in messages]),
                        'type': 'warning',
                        'sticky': True,
                    },
                }

            # Guardar datos en la BD
            # self.env['gl.social.reports'].create({
            #     'partner_id': self.partner_id.id,
            #     'date_start': self.date_start,
            #     'date_end': self.date,
            #     'report_generated': not has_errors,
            #     'data_json': data,
            # })

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
