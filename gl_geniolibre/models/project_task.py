# -*- coding: utf-8 -*-:
import random, re, requests, base64, boto3, json, logging

from io import BytesIO
from odoo.tools import html2plaintext
from odoo import models, fields, api
from datetime import datetime
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

API_VERSION = "v23.0"
LinkedIn_Version = "202505"


class red_social(models.Model):
    _name = 'red.social'
    _description = 'Redes Sociales'
    name = fields.Char(string='Nombre', required=True)

    @api.model
    def _auto_init(self):
        """Crear redes sociales por defecto si faltan"""
        res = super()._auto_init()

        redes_por_defecto = [
            'Facebook',
            'Instagram',
            'LinkedIn',
            'TikTok',
        ]

        # Buscar nombres ya existentes (case insensitive por si acaso)
        existentes = self.search([]).mapped('name')
        existentes = [nombre.strip().lower() for nombre in existentes]

        redes_a_crear = [{
            'name': nombre
        } for nombre in redes_por_defecto if nombre.lower() not in existentes]

        if redes_a_crear:
            self.create(redes_a_crear)

        return res


class project_task(models.Model):
    _inherit = "project.task"
    fecha_publicacion = fields.Datetime("Fecha y hora de Publicación", tracking=True, default=lambda self: fields.Datetime.now())
    inicio_promocion = fields.Date("Inicio de Promoción", tracking=True)
    fin_promocion = fields.Date("Fin de Promoción", tracking=True)
    presupuesto = fields.Monetary("Presupuesto", currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda')
    adjuntos_ids = fields.Many2many('ir.attachment', string='Archivos Adjuntos', tracking=True)
    imagen_portada = fields.Image(string='Imagen de Portada')
    tipo = fields.Selection(selection=[
        ('feed', 'Feed'),
        ('video_stories', 'Historia'),
        ('video_reels', 'Reel'),
        ('otro', 'Otro')
    ], string='Tipo de Publicación', default='otro', required=True)
    red_social_ids = fields.Many2many('red.social', string='Redes Sociales', )
    hashtags = fields.Text(string="Hashtags")
    texto_en_diseno = fields.Html(string="Texto en diseño")
    partner_id = fields.Many2one('res.partner')
    partner_page_access_token = fields.Char(related="partner_id.facebook_page_access_token")
    partner_facebook_page_id = fields.Char(related="partner_id.facebook_page_id")
    partner_instagram_page_id = fields.Char(related="partner_id.instagram_page_id")
    partner_tiktok_access_token = fields.Char(related="partner_id.tiktok_access_token")
    partner_linkedin_page_id = fields.Char(related="partner_id.id_linkedin_organization")

    post_estado = fields.Char(string="Estado de la Publicación", default="Pendiente")
    fb_post_id = fields.Char(string="Facebook Post ID")
    fb_post_url = fields.Char(string="Facebook URL")
    fb_video_id = fields.Char(string="Facebook Video ID")
    fb_video_url = fields.Char(string="Facebook Video URL")
    inst_post_id = fields.Char(string="Instagram Post ID")
    inst_post_url = fields.Char(string="Instagram URL")
    tiktok_post_id = fields.Char(string="TikTok Post ID")
    tiktok_post_url = fields.Char(string="TikTok URL")

    def copy(self, default=None):
        self.ensure_one()
        # Es más seguro comprobar si project_id existe antes de acceder a sus atributos
        if self.project_id and self.project_id.project_type == 'marketing':
            raise ValidationError("No se puede duplicar tareas de proyectos de tipo Marketing.")
        # Usar la sintaxis de super() preferida en Python 3
        return super().copy(default)

    def write(self, vals):  # optimizado

        for record in self:
            current_tipo = vals.get('tipo', record.tipo)

            # Validación condicional para fecha_publicacion
            if current_tipo != "otro":
                # Verificar si fecha_publicacion está en vals o si ya tiene un valor en el registro
                fecha_publicacion_valor = vals.get('fecha_publicacion', record.fecha_publicacion)
                if not fecha_publicacion_valor:
                    raise ValidationError("La 'Fecha y hora de Publicación' es obligatoria cuando el tipo no es 'Otro'.")

            if record.state == "03_approved":
                if current_tipo == "otro":
                    continue

                if 'adjuntos_ids' in vals:
                    current_attachment_ids = set(record.adjuntos_ids.ids)
                    for command in vals['adjuntos_ids']:
                        op_type = command[0]
                        if op_type == 0:
                            pass
                        elif op_type == 1:
                            pass
                        elif op_type == 2:
                            if command[1]:
                                current_attachment_ids.discard(command[1])
                        elif op_type == 3:
                            if command[1]:
                                current_attachment_ids.discard(command[1])
                        elif op_type == 4:
                            if command[1]:
                                current_attachment_ids.add(command[1])
                        elif op_type == 5:
                            current_attachment_ids.clear()
                        elif op_type == 6:
                            current_attachment_ids = set(command[2])

                    current_attachments = record.env['ir.attachment'].browse(list(current_attachment_ids))
                else:
                    current_attachments = record.adjuntos_ids

                if not current_attachments:
                    raise ValidationError("Debe seleccionar al menos un archivo para publicar para el tipo '{}'.".format(current_tipo))

                if current_tipo != "feed":
                    if len(current_attachments) > 1:
                        raise ValidationError("Solo se acepta 1 archivo para el tipo de publicación '{}'.".format(current_tipo))
                    if current_tipo in [
                        "video_stories",
                        "video_reels"
                    ]:
                        for attachment in current_attachments:
                            if attachment.mimetype != "video/mp4":
                                raise ValidationError("Solo se aceptan videos en formato MP4 para el tipo de publicación '{}'.".format(current_tipo))
                else:  # current_tipo == "feed"
                    for attachment in current_attachments:
                        if attachment.mimetype == "video/mp4":
                            raise ValidationError("Solo se aceptan imágenes para publicaciones de tipo 'Feed'. No se permiten videos MP4.")
        return super().write(vals)

    def programar_post(self):
        self.ensure_one()  # Asegurar que operamos sobre un único registro al principio

        if self.state != "03_approved":
            raise ValidationError("El estado de la Tarea debe ser 'Aprobado' para poder programar el post.")

        # Eliminar la siguiente línea: Odoo manejará el commit de la transacción.
        self.post_estado = "Programado"  # Opcional: Si este metodo se llama desde un botón y quieres dar feedback  # podrías devolver una acción de notificación, pero para la lógica del modelo  # simplemente cambiar el estado es suficiente.

    def cancelar_post(self):
        self.ensure_one()  # Asegura que solo hay un registro seleccionado
        self.post_estado = "Pendiente"

    def revisar_post(self, from_cron=False):  # Optimizado
        error_message = []
        try:
            if self.post_estado == "Procesando":
                # 2. Verificar el estado de procesamiento
                base_url = f'https://graph.facebook.com/{API_VERSION}'
                status_url = f"{base_url}/{self.inst_post_id}"
                status_params = {
                    "access_token": self.partner_page_access_token,
                    "fields": "status_code"
                }
                status_response = requests.get(status_url, params=status_params)
                status_data = status_response.json()

                status_code = status_data.get('status_code')
                if status_code == 'FINISHED':
                    # Publicación inmediata
                    publish_params = {
                        'access_token': self.partner_page_access_token,
                        'creation_id': self.inst_post_id,
                    }
                    publish_url = f"{base_url}/{self.partner_instagram_page_id}/media_publish"
                    publish_response = requests.post(publish_url, params=publish_params)

                    if publish_response.status_code == 200:
                        self.inst_post_id = publish_response.json().get('id')
                        self.post_estado = 'Publicado'
                    else:
                        error_message.append(publish_response.json().get('error', {}).get('message', 'Error desconocido'))
                        raise ValidationError(error_message)
                elif status_code == 'ERROR':
                    self.post_estado = 'Error'
                    self.state = '01_in_progress'
                    raise ValidationError(status_data)
                else:
                    raise ValidationError(status_data)

            # Generar Permalink de Facebook
            if self.fb_post_id and self.post_estado == "Publicado":
                self.fb_post_url = f"https://www.facebook.com/{self.fb_post_id}" if self.tipo != "video_stories" else f"https://www.facebook.com/{self.partner_facebook_page_id}"

            # Generar Permalink de Instagram
            if self.inst_post_id and self.post_estado == "Publicado" and not self.inst_post_url:
                url = f"https://graph.facebook.com/{API_VERSION}/{self.inst_post_id}"
                params = {
                    'fields': 'media_type,permalink,username',
                    'access_token': self.partner_page_access_token
                }
                response = requests.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('media_type') == "STORY":
                        username = data.get('username')
                        self.inst_post_url = f"https://www.instagram.com/{username}/" if username else False
                    else:
                        self.inst_post_url = data.get('permalink')
                else:
                    error_message.append(response.json())

            # Generar Permalink de TikTok
            if self.tiktok_post_id and self.post_estado == "Publicado" and not self.tiktok_post_url:
                status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
                headers = {
                    'Authorization': f'Bearer {self.partner_tiktok_access_token}',
                    'Content-Type': 'application/json',
                }
                payload = {
                    "publish_id": self.tiktok_post_id
                }
                response = requests.post(status_url, headers=headers, json=payload)

                if response.status_code == 200 and response.json().get('data', {}).get('status') == 'PUBLISH_COMPLETE':
                    video_id = response.json().get("data", {}).get("publicaly_available_post_id")
                    if video_id:
                        video_query_url = "https://open.tiktokapis.com/v2/video/query/"
                        payload = {
                            "filters": {
                                "video_ids": [
                                    video_id.strip("[]")
                                ]
                            }
                        }
                        params = {
                            'fields': "share_url"
                        }
                        video_response = requests.post(video_query_url, headers=headers, params=params, json=payload)

                        if video_response.status_code == 200:
                            video_data = video_response.json().get('data', {}).get('videos', [])
                            if video_data:
                                self.tiktok_post_url = video_data[0].get('share_url')
                        else:
                            error_message.append(video_response.json().get('error', {}).get('message', 'Error desconocido en TikTok'))
                    else:
                        error_message.append("No se pudo obtener el video_id para esta publicación.")
                else:
                    error_message.append("El video aún no fue procesado")

            # Mostrar errores acumulados si los hay
            if error_message:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Error Inesperado",
                        "message": '\n'.join([str(error) for error in error_message]),
                        "type": "danger",
                        "sticky": True,
                        'next': {
                            'type': 'ir.actions.act_window_close'
                        },
                    },
                }

            # En caso de éxito
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Publicación Revisada",
                    "message": "Las URL fueron actualizadas",
                    "type": "success",
                    'next': {
                        'type': 'ir.actions.act_window_close'
                    },
                },
            }

        except Exception as e:
            _logger.error(f"Error en revisar_post para registro {self.id}: {str(e)}")
            if from_cron:
                raise
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Error Inesperado",
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                    'next': {
                        'type': 'ir.actions.act_window_close'
                    },
                },
            }

    def publicar_post(self):
        BASE_URL = f'https://graph.facebook.com/{API_VERSION}'

        def remove_duplicate_links(text):
            seen_urls = set()

            def replace_link(match):
                url = match.group(0)
                if url in seen_urls:
                    return ''
                seen_urls.add(url)
                return url

            # Eliminar enlaces duplicados
            text_without_duplicates = re.sub(r'https?://\S+', replace_link, text)
            text_cleaned = re.sub(r'\[\d+\]', '', text_without_duplicates)

            return text_cleaned

        # Funciones
        def upload_images_to_facebook(attachment):

            image_bytes = base64.b64decode(attachment.datas)
            files = {
                'source': ("image.jpg", image_bytes, "image/jpeg")  # File name and MIME type
            }
            data = {
                "access_token": self.partner_page_access_token,
                "published": False,
                "temporary": True,
            }
            url = f"{BASE_URL}/{self.partner_facebook_page_id}/photos"
            response_upload = requests.post(url, files=files, data=data)
            if response_upload.status_code == 200:
                return response_upload.json().get('id')
            else:
                raise Exception(f"Error al subir una imagen en Facebook: {response_upload.json()}")

        def publish_on_facebook(media_ids):

            url = f"{BASE_URL}/{self.partner_facebook_page_id}/{self.tipo}"
            if self.tipo == "feed":
                params = {
                    'access_token': self.partner_page_access_token,
                    'message': combined_text,
                    'attached_media': str([{
                        'media_fbid': media_id
                    } for media_id in media_ids]),
                    'published': True,  # Set to False for scheduling
                }

                response = requests.post(url, params=params)
                response_data = response.json()
                if response.status_code == 200:
                    return response.json().get("id")
                else:
                    raise ValidationError(f"Error al publicar Feed en Facebook: {response_data}")
            else:
                # Initialize an Upload Session
                headers = {
                    "Content-Type": "application/json",
                }
                params = {
                    "upload_phase": "start",
                    "access_token": self.partner_page_access_token
                }
                response = requests.post(url, data=headers, params=params)
                response_data = response.json()
                if 'video_id' in response_data and 'upload_url' in response_data:
                    video_id = response_data['video_id']
                    self.fb_video_id = video_id
                    upload_url = response_data['upload_url']
                else:
                    raise ValidationError(f"Error Starting session: {response_data}")

                # Upload a Hosted File
                headers = {
                    "Authorization": f"OAuth {self.partner_page_access_token}",
                    "file_url": media_ids[0],
                }
                response = requests.post(upload_url, headers=headers)
                response_data = response.json()
                if 'success' not in response_data:
                    raise ValidationError(f"Error uploading video file: {response_data}")

                params = {
                    "access_token": self.partner_page_access_token,
                    "video_id": video_id,
                    "upload_phase": "finish",
                    "video_state": "PUBLISHED",
                    "description": combined_text,
                }
                response = requests.post(url, params=params)
                response_data = response.json()
                if 'success' in response_data:
                    if self.imagen_portada and self.tipo == "video_reels":
                        image_data = base64.b64decode(self.imagen_portada)
                        image_file = BytesIO(image_data)
                        image_file.name = 'miniatura.jpg'  # necesario para el multipart/form-data

                        url = f"https://graph.facebook.com/{API_VERSION}/{video_id}/thumbnails"
                        files = {
                            'source': ('miniatura.jpg', image_file, 'image/jpeg')
                        }
                        data = {
                            'access_token': self.partner_page_access_token,
                            'is_preferred': 'true'
                        }
                        response = requests.post(url, files=files, data=data)
                    return response_data.get("post_id")

                else:
                    raise ValidationError(f"Error al publicar Reel en Facebook: {response_data}")

        def publish_on_instagram(media_urls):
            estado_procesando = False
            carousel_ids = []
            container_url = f"{BASE_URL}/{self.partner_instagram_page_id}/media"
            # Step 1: Create media container
            if len(media_urls) == 1:
                if self.tipo == "feed":
                    container_params = {
                        'access_token': self.partner_page_access_token,
                        'caption': combined_text,
                        'image_url': media_urls[0],  # For images
                        'published': True,  # Important for scheduling
                    }
                else:
                    estado_procesando = True

                    if self.tipo == "video_stories":
                        container_params = {
                            'access_token': self.partner_page_access_token,
                            'caption': combined_text,
                            'video_url': media_urls[0],  # For images
                            'published': True,  # Important for scheduling,
                            'media_type': 'STORIES'
                        }
                    else:  # Publicación de Reels
                        cover_url = upload_files_to_s3([("portada.jpg", self.imagen_portada)], aws_api, aws_secret)[0]
                        container_params = {
                            'access_token': self.partner_page_access_token,
                            'caption': combined_text,
                            'video_url': media_urls[0],  # For images
                            'published': True,  # Important for scheduling,
                            'media_type': 'REELS',
                            "cover_url": cover_url
                        }

                container_response = requests.post(container_url, params=container_params)
                container_id = container_response.json().get('id')
                if container_response.status_code != 200:
                    error_message = container_response.json()
                    raise ValidationError(f"Error al crear el contenedor de Instagram: {error_message}")

            else:
                for url in media_urls:
                    carousel_params = {
                        'access_token': self.partner_page_access_token,
                        'is_carousel_item': 'true',
                        'image_url': url,  # For images
                    }
                    carousel_response = requests.post(container_url, params=carousel_params)
                    carousel_id = carousel_response.json().get('id')
                    carousel_ids.append(carousel_response.json()['id'])
                carousel_params = {
                    'media_type': 'CAROUSEL',
                    'children': ",".join(carousel_ids),  # Join all IDs with commas
                    'caption': combined_text,
                    'access_token': self.partner_page_access_token
                }

                container_response = requests.post(container_url, carousel_params)
                container_id = container_response.json()['id']

            if not estado_procesando:

                # For immediate publishing (without scheduling)
                publish_params = {
                    'access_token': self.partner_page_access_token,
                    'creation_id': container_id,
                }

                publish_url = f"{BASE_URL}/{self.partner_instagram_page_id}/media_publish"
                publish_response = requests.post(publish_url, params=publish_params)

                if publish_response.status_code != 200:
                    error_message = publish_response.json().get('error', {}).get('message', 'Unknown error')
                    raise ValidationError(f"Error al publicar en Instagram: {error_message}")

                return publish_response.json().get('id')
            else:

                return container_id, estado_procesando

        def publish_on_tiktok(media_urls):
            url = "https://open.tiktokapis.com/v2/post/publish/video/init/"

            headers = {
                "Authorization": f"Bearer {self.partner_tiktok_access_token}",
                "Content-Type": "application/json; charset=UTF-8"
            }

            data = {
                "post_info": {
                    "title": combined_text,
                    "privacy_level": "SELF_ONLY",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": media_urls[0],
                }
            }
            tiktok_response = requests.post(url, headers=headers, json=data)
            response_data = tiktok_response.json()
            if tiktok_response.status_code != 200:
                raise ValidationError(f"Error al Publicar el video en TIKTOK: {response_data}")
            # You can then check the response
            return response_data["data"]["publish_id"]

        def publish_on_linkedin(media_urls):
            linkedin_access_token = self.env['ir.config_parameter'].sudo().get_param('linkedin.access_token')
            ORG_URN = "urn:li:organization:" + self.partner_linkedin_page_id  # Replace with your organization URN
            # Headers for all requests
            headers = {
                "Authorization": f"Bearer {linkedin_access_token}",
                "LinkedIn-Version": LinkedIn_Version,
                "X-RestLi-Protocol-Version": "2.0.0",
                "Content-Type": "application/json"
            }

            # 1. Initialize image upload
            init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
            init_data = {
                "initializeUploadRequest": {
                    "owner": ORG_URN
                }
            }

            try:
                # Initialize upload
                init_response = requests.post(init_url, headers=headers, json=init_data)
                init_response.raise_for_status()

                # Extract values from response
                upload_url = init_response.json()["value"]["uploadUrl"]
                image_urn = init_response.json()["value"]["image"]

                # 2. Upload the image
                image_data = requests.get(media_urls[0]).content
                upload_headers = {
                    "Authorization": f"Bearer {linkedin_access_token}",
                    "Content-Type": "image/jpeg"
                }

                upload_response = requests.put(upload_url, headers=upload_headers, data=image_data)
                upload_response.raise_for_status()

                # 3. Create post with the image
                post_url = "https://api.linkedin.com/rest/posts"
                post_data = {
                    "author": ORG_URN,
                    "commentary": "Texto de tu publicación con imagen en LinkedIn!",
                    "visibility": "PUBLIC",
                    "distribution": {
                        "feedDistribution": "MAIN_FEED",
                        "targetEntities": [],
                        "thirdPartyDistributionChannels": []
                    },
                    "content": {
                        "media": {
                            "title": "Título de la imagen",
                            "id": image_urn
                        }
                    },
                    "lifecycleState": "PUBLISHED",
                    "isReshareDisabledByAuthor": False
                }

                post_response = requests.post(post_url, headers=headers, json=post_data)
                post_response.raise_for_status()
            except requests.exceptions.HTTPError as err:
                print(f"Response content: {err.response.text}")
            except Exception as e:
                print(f"An error occurred: {str(e)}")

        # Validaciones iniciales (detienen todo el proceso si fallan)
        if self.fecha_publicacion > fields.Datetime.now():
            return

        if not self.fecha_publicacion:
            raise ValidationError("Debe seleccionar una fecha de publicación")

        if self.state != "03_approved":
            raise ValidationError("El estado de la Tarea debe ser 'Aprobado'")

        if not self.red_social_ids:
            raise ValidationError("Debe seleccionar al menos una red social")

        try:
            # Configuración inicial
            self.write({ 'post_estado': 'Error' })
            parametros = self.env['ir.config_parameter'].sudo()
            aws_api = parametros.get_param('gl_aws.api_key')
            aws_secret = parametros.get_param('gl_aws.secret')

            # Preparación del texto
            plain_description = html2plaintext(self.description or '')
            plain_hashtags = html2plaintext(self.hashtags or '')
            paragraphs = [p.strip() for p in plain_description.split('\n') if p.strip()]
            formatted_description = '\n\n'.join(paragraphs)
            formatted_description = remove_duplicate_links(formatted_description).rstrip()
            combined_text = f"{formatted_description}\n\n{plain_hashtags}"

            # Validación de credenciales por red social
            credential_errors = []
            if 'Facebook' in self.red_social_ids.mapped('name') and not self.partner_facebook_page_id:
                credential_errors.append("Facebook")
            if 'Instagram' in self.red_social_ids.mapped('name') and not self.partner_instagram_page_id:
                credential_errors.append("Instagram")
            if 'TikTok' in self.red_social_ids.mapped('name') and not self.partner_tiktok_access_token:
                credential_errors.append("TikTok")
            if 'LinkedIn' in self.red_social_ids.mapped('name') and not self.partner_linkedin_page_id:
                credential_errors.append("LinkedIn")

            if credential_errors:
                raise ValidationError(f"Los datos de acceso no fueron configurados para: {', '.join(credential_errors)}")

            # Subir archivos a S3 (única operación que debe fallar completamente si hay error)
            media_urls = upload_files_to_s3(self.adjuntos_ids, aws_api, aws_secret)
            media_ids = []

            # Publicación en redes sociales con gestión de errores individual
            errors = []
            success_messages = []
            published_on = []

            procesando = False

            # Facebook
            if 'Facebook' in self.red_social_ids.mapped('name'):
                try:
                    if self.tipo == "feed":
                        for attachment in self.adjuntos_ids:
                            media_id = upload_images_to_facebook(attachment)  # Pass single attachment
                            media_ids.append(media_id)
                        fb_response = publish_on_facebook(media_ids)

                    else:
                        fb_response = publish_on_facebook(media_urls)

                    if fb_response:

                        if not self.tipo == "video_stories":
                            self.write({
                                'fb_post_id': fb_response,
                                'fb_post_url': f'https://www.facebook.com/{fb_response}',
                            })
                        else:

                            self.fb_post_url = f"https://www.facebook.com/{self.partner_facebook_page_id}"

                        success_messages.append("Facebook: Publicación exitosa")
                        published_on.append("Facebook")
                    else:
                        errors.append("Facebook: No se recibió respuesta del servidor")
                except Exception as e:
                    errors.append(f"Facebook: {str(e)}")

            # Instagram
            if 'Instagram' in self.red_social_ids.mapped('name'):

                try:
                    instagram_result = publish_on_instagram(media_urls)

                    if isinstance(instagram_result, tuple):  # Cuando es video (procesando=True)
                        container_id, procesando = instagram_result
                        self.write({
                            'inst_post_id': container_id,
                        })
                        success_messages.append("Instagram: Publicación en proceso" if procesando else "Instagram: Publicación exitosa")
                        published_on.append("Instagram")
                    else:  # Cuando es imagen normal
                        self.write({
                            'inst_post_id': instagram_result,
                        })
                        success_messages.append("Instagram: Publicación exitosa")
                        published_on.append("Instagram")

                except Exception as e:
                    errors.append(f"Instagram: {str(e)}")

            # TikTok
            if 'TikTok' in self.red_social_ids.mapped('name') and self.tipo == "video_reels":
                try:
                    tik_response = publish_on_tiktok(media_urls)
                    if tik_response:
                        self.write({
                            'tiktok_post_id': tik_response
                        })
                        success_messages.append("TikTok: Publicación exitosa")
                        published_on.append("TikTok")
                    else:
                        errors.append("TikTok: No se recibió respuesta del servidor")
                except Exception as e:
                    errors.append(f"TikTok: {str(e)}")

            # LinkedIn
            if 'LinkedIn' in self.red_social_ids.mapped('name'):
                try:
                    linkedin_response = publish_on_linkedin(media_urls)
                    if linkedin_response:
                        self.write({
                            'linkedin_post_id': linkedin_response,
                            'linkedin_post_url': f'https://www.linkedin.com/feed/update/{linkedin_response}'
                        })
                        success_messages.append("LinkedIn: Publicación exitosa")
                        published_on.append("LinkedIn")
                    else:
                        errors.append("LinkedIn: No se recibió respuesta del servidor")
                except Exception as e:
                    errors.append(f"LinkedIn: {str(e)}")

            # Resultado final
            if published_on:
                self.write({
                    'post_estado': 'Procesando' if procesando else 'Publicado'
                })
                if errors:
                    # Publicación parcialmente exitosa
                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Error inesperado",
                            'message': '\n'.join(success_messages + [
                                "Errores:"
                            ] + errors),
                            "type": "danger",
                            "sticky": True,
                        },
                    }
                else:
                    # Todo exitoso
                    return {
                        'effect': {
                            'message': f"Contenido publicado en: {', '.join(published_on)}",
                            'fadeout': 'slow',
                            'type': 'rainbow_man',
                            'next': {
                                'type': 'ir.actions.act_window_close'
                            },
                        }
                    }
            else:
                # Todo falló
                raise ValidationError("No se pudo publicar en ninguna red social:\n" + "\n".join(errors))

        except Exception as e:
            raise ValidationError(f"Error en el proceso de publicación: {str(e)}")


def upload_files_to_s3(files, aws_api, aws_secret):
    aws_access_key_id = aws_api
    aws_secret_access_key = aws_secret
    bucket_name = 'odoo-geniolibre'
    region_name = 'us-east-2'

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValidationError("No se configuró correctamente el servicio de AWS.")

    s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=region_name)

    if not files:
        raise ValidationError("No se encontraron archivos adjuntos o imágenes.")

    # Normalizar archivos: convertir a lista si es recordset o cualquier otra cosa iterable
    if hasattr(files, 'ids'):  # Odoo recordset
        files = list(files)
    elif isinstance(files, (tuple, list)):
        # Asegurar que sea lista, no una tupla inmutable
        files = list(files)
    else:
        files = [
            files
        ]

    if hasattr(files, 'ids'):
        files = list(files)
    elif not isinstance(files, list):
        files = [
            files
        ]

    allowed_extensions = {
        'jpg',
        'jpeg',
        'mp4'
    }
    uploaded_urls = []

    # Identificadores comunes
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_digits = ''.join(random.choices('0123456789', k=5))

    for idx, item in enumerate(files, start=1):
        if hasattr(item, 'datas') and hasattr(item, 'name'):  # ir.attachment
            file_name_raw = item.name
            file_data = item.datas
        elif isinstance(item, (tuple, list)) and len(item) == 2:  # (name, data)
            file_name_raw = item[0]
            file_data = item[1]
        elif isinstance(item, str):  # base64 string
            file_name_raw = f"upload_{timestamp}_{random_digits}-{idx}.jpg"
            file_data = item
        else:
            raise ValidationError("Formato de archivo no soportado o inválido.")

        file_ext = file_name_raw.split('.')[-1].lower()
        if file_ext not in allowed_extensions:
            raise ValidationError(f"Tipo de archivo '{file_ext}' no permitido. Solo JPG, JPEG o MP4.")

        file_name = f"media_{timestamp}_{random_digits}-{idx}.{file_ext}"

        try:
            s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=base64.b64decode(file_data), )
        except Exception as e:
            raise ValidationError(f"Error al subir archivo {file_name_raw} a S3: {str(e)}")

        file_url = f"https://{bucket_name}.s3.{region_name}.amazonaws.com/{file_name}"
        uploaded_urls.append(file_url)

    return uploaded_urls
