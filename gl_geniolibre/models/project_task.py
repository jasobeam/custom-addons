# -*- coding: utf-8 -*-:
import random
import re, requests, base64, boto3, json

from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tools import html2plaintext
from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


class red_social(models.Model):
    _name = 'red.social'
    _description = 'Redes Sociales'
    name = fields.Char(string='Nombre', required=True)

    @api.model
    def _auto_init(self):
        """Create default social networks if table is empty"""
        res = super()._auto_init()
        if not self.search_count([]):
            self.create([
                {
                    'name': 'Facebook'
                },  # {'name': 'Twitter'},
                {
                    'name': 'Instagram'
                },  # {'name': 'LinkedIn'},
                # {'name': 'YouTube'},
                {
                    'name': 'TikTok'
                },
            ])
        return res


class project_task(models.Model):
    _inherit = "project.task"
    fecha_publicacion = fields.Datetime("Fecha y hora de Publicación", tracking=True, default=lambda self: fields.Datetime.now())
    inicio_promocion = fields.Date("Inicio de Promoción", tracking=True)
    fin_promocion = fields.Date("Fin de Promoción", tracking=True)
    presupuesto = fields.Monetary("Presupuesto", currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda')
    adjuntos_ids = fields.Many2many('ir.attachment', string='Archivos Adjuntos', tracking=True)
    milisegundos_portada = fields.Integer(string='Milisegundos para Miniatura')
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
        if self.project_id.project_type == 'marketing':
            raise ValidationError("No se puede duplicar tareas de proyectos de tipo Marketing.")
        return super(project_task, self).copy(default)

    def write(self, vals):

        for record in self:
            if self.state != "03_approved":
                return super().write(vals)

            # Get the new values or fall back to existing ones
            current_tipo = vals.get('tipo', record.tipo)

            # Handle attachments properly
            if 'adjuntos_ids' in vals:
                # Create a set of current attachment IDs for easier manipulation
                current_attachment_ids = set(record.adjuntos_ids.ids)

                # Process each command
                for cmd in vals['adjuntos_ids']:
                    if cmd[0] == 3:  # UNLINK (delete)
                        current_attachment_ids.discard(cmd[1])
                    elif cmd[0] == 4:  # LINK (add)
                        current_attachment_ids.add(cmd[1])
                    elif cmd[0] == 6:  # REPLACE
                        current_attachment_ids = set(cmd[2])

                # Get the final attachment records
                current_attachments = self.env['ir.attachment'].browse(list(current_attachment_ids))
            else:
                current_attachments = record.adjuntos_ids

            # Skip validation for "otro" tipo
            if current_tipo == "otro":
                return

            # Validate attachments exist
            if len(current_attachments) < 1:
                raise ValidationError("Debe seleccionar un archivo para publicar")
            # Validate attachment types
            if current_tipo != "feed":
                if len(current_attachments) > 1 and len(self.adjuntos_ids) > 0:
                    raise ValidationError("Solo se acepta 1 archivo para este tipo de publicación.")
                if current_tipo in [
                    "video_stories",
                    "reels"
                ]:
                    for attachment in current_attachments:
                        if attachment.mimetype != "video/mp4":
                            raise ValidationError("Solo se aceptan videos en formato MP4 para este tipo de publicación.")

            else:
                for attachment in current_attachments:
                    if attachment.mimetype == "video/mp4":
                        raise ValidationError("Solo se aceptan imágenes para publicaciones de tipo 'Feed'.")

        # Proceed with a normal save operation
        return super().write(vals)

    def programar_post(self):
        if self.state != "03_approved":
            raise ValidationError("El estado de la Tarea debe ser 'Aprobado'")

        self.ensure_one()  # Asegura que solo hay un registro seleccionado
        self.env.cr.commit()  # Guarda la transacción en la base de datos
        self.post_estado = "Programado"

    def cancelar_post(self):

        self.ensure_one()  # Asegura que solo hay un registro seleccionado
        self.env.cr.commit()  # Guarda la transacción en la base de datos
        self.post_estado = "Pendiente"

    def revisar_post(self, from_cron=False):
        error_message = []
        try:
            if self.post_estado == "Procesando":
                # 2. Check processing status
                BASE_URL = 'https://graph.facebook.com/v22.0'
                container_id = self.inst_post_id
                status_url = f"https://graph.facebook.com/v22.0/{container_id}"
                status_params = {
                    "access_token": self.partner_page_access_token,
                    "fields": "status_code"
                }
                status_response = requests.get(status_url, params=status_params)
                status_data = status_response.json()
                if status_data.get('status_code') == 'FINISHED':
                    # For immediate publishing (without scheduling)
                    publish_params = {
                        'access_token': self.partner_page_access_token,
                        'creation_id': self.inst_post_id,
                    }

                    publish_url = f"{BASE_URL}/{self.partner_instagram_page_id}/media_publish"
                    publish_response = requests.post(publish_url, params=publish_params)

                    if publish_response.status_code != 200:
                        error_message = publish_response.json().get('error', {}).get('message', 'Unknown error')
                        raise ValidationError(error_message)
                    else:
                        self.inst_post_id = publish_response.json().get('id')
                        self.write({
                            'post_estado': 'Publicado',
                        })

                elif status_data.get('status_code') == 'ERROR':
                    self.write({
                        'post_estado': 'Error',
                        'state': '01_in_progress'
                    })
                    error_message = status_data
                    raise ValidationError(error_message)
                else:
                    raise ValidationError(status_data)

            # Get Facebook Permalink
            if self.fb_post_id and self.post_estado == "Publicado":
                print(self.tipo)
                if not self.tipo == "video_stories":
                    self.fb_post_url = 'https://www.facebook.com/' + self.fb_post_id
                else:
                    self.fb_post_url = 'Las historias no tienen acceso directo'

            # Get Instagram Permalink
            if self.inst_post_id and self.post_estado == "Publicado":
                if not self.inst_post_url:
                    url = f"https://graph.facebook.com/v22.0/{self.inst_post_id}"
                    # Parameters
                    params = {
                        'fields': 'permalink',
                        'access_token': self.partner_page_access_token
                    }
                    response = requests.get(url, params=params)
                    if response.status_code != 200:
                        error_message.append(response.json())
                    else:
                        data = response.json()
                        self.inst_post_url = data.get('permalink')

            # Get TIKTOK Permalink
            if self.tiktok_post_id and self.post_estado == "Publicado":

                if not self.tiktok_post_url:
                    # Paso 1: Obtener el video_id desde el publish_id
                    status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
                    headers = {
                        'Authorization': f'Bearer {self.partner_tiktok_access_token}',
                        'Content-Type': 'application/json',
                    }
                    data = {
                        "publish_id": self.tiktok_post_id,
                    }
                    response = requests.post(status_url, headers=headers, data=json.dumps(data))
                    if response.status_code != 200:
                        error_message.append(response.json())

                    elif response.json().get('data', {}).get('status') == 'PUBLISH_COMPLETE':
                        status_data = response.json()
                        video_id = status_data.get("data", {}).get("publicaly_available_post_id")
                        if not video_id:
                            error_message.append("No se pudo obtener el video_id para esta publicación.")

                        video_id = str(video_id)
                        video_id = video_id.strip("[]")
                        url = "https://open.tiktokapis.com/v2/video/query/"
                        headers = {
                            'Authorization': f'Bearer {self.partner_tiktok_access_token}',
                            'Content-Type': 'application/json'
                        }
                        params = {
                            'fields': "share_url"
                        }
                        payload = {
                            "filters": {
                                "video_ids": [
                                    str(video_id)
                                ]
                            }
                        }
                        # 4. Enviar y procesar respuesta
                        response = requests.post(url, headers=headers, params=params, json=payload, timeout=10)
                        if response.status_code == 200:
                            # Extraer el permalink
                            video_data = response.json().get('data', {}).get('videos', [])
                            if video_data:
                                self.tiktok_post_url = video_data[0].get('share_url')

                        else:
                            error = response.json().get('error', {})
                            error_message.append(f"Error TikTok API: {error.get('message')}")
                    else:
                        error_message.append("El video aun no fue procesado")

            if error_message:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Error Inesperado",
                        "message": f"Error: {error_message}",
                        "type": "danger",
                        "sticky": True,
                        'next': {
                            'type': 'ir.actions.act_window_close'
                        },
                    },
                }
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
            # Si es ejecución desde cron, relanzar la excepción
            if from_cron:
                raise

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Error Inesperado",
                    "message": f"Error: {e}",
                    "type": "danger",
                    "sticky": True,
                    'next': {
                        'type': 'ir.actions.act_window_close'
                    },
                },
            }

    def publicar_post(self):
        BASE_URL = 'https://graph.facebook.com/v22.0'

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
                    "thumb_offset" : self.milisegundos_portada
                    }
                response = requests.post(url, params=params)
                response_data = response.json()
                if 'success' in response_data:
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
                    else:
                        container_params = {
                            'access_token': self.partner_page_access_token,
                            'caption': combined_text,
                            'video_url': media_urls[0],  # For images
                            'published': True,  # Important for scheduling,
                            'media_type': 'REELS',
                            'thumbNailOffset': 30000,
                            'thumbNail': "https://img.ayrshare.com/012/gb.jpg"
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
                print(container_id)
                print(estado_procesando)
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

        # Validaciones iniciales (detienen todo el proceso si fallan)
        if self.fecha_publicacion > fields.Datetime.now():
            return False  # Salir sin publicar

        if self.state != "03_approved":
            raise ValidationError("El estado de la Tarea debe ser 'Aprobado'")

        if not self.red_social_ids:
            raise ValidationError("Debe seleccionar al menos una red social")

        try:
            # Configuración inicial
            self.write({
                'post_estado': 'Error'
            })
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
            if 'TikTok' in self.red_social_ids.mapped('name') and not self.partner_instagram_page_id:
                credential_errors.append("TikTok")

            if credential_errors:
                raise ValidationError(f"Los datos de acceso no fueron configurados para: {', '.join(credential_errors)}")

            # Subir archivos a S3 (única operación que debe fallar completamente si hay error)
            media_urls = upload_files_to_s3(self.adjuntos_ids, aws_api, aws_secret)
            media_ids = []

            # Publicación en redes sociales con gestión de errores individual
            errors = []
            success_messages = []
            published_on = []
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
                            self.fb_post_url = 'Las historias no tienen acceso directo'

                        success_messages.append("Facebook: Publicación exitosa")
                        published_on.append("Facebook")
                        print("Facebook OK")
                    else:
                        errors.append("Facebook: No se recibió respuesta del servidor")
                except Exception as e:
                    errors.append(f"Facebook: {str(e)}")
            procesando=False
            # Instagram
            if 'Instagram' in self.red_social_ids.mapped('name'):
                try:
                    instagram_result = publish_on_instagram(media_urls)

                    if isinstance(instagram_result, tuple):  # Cuando es video (procesando=True)
                        container_id, procesando = instagram_result
                        print(instagram_result)
                        print(procesando)
                        print(container_id)
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
                        print("TikTok OK")
                    else:
                        errors.append("TikTok: No se recibió respuesta del servidor")
                except Exception as e:
                    errors.append(f"TikTok: {str(e)}")

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


def upload_files_to_s3(file, aws_api, aws_secret):
    aws_access_key_id = aws_api
    aws_secret_access_key = aws_secret
    bucket_name = 'odoo-geniolibre'
    region_name = 'us-east-2'

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValidationError("No se configuró correctamente el servicio de AWS")

    # Initialize the S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name
    )

    if not file:
        raise ValidationError("No se encontraron archivos adjuntos.")

    allowed_extensions = {'jpg', 'jpeg', 'mp4'}
    uploaded_urls = []

    # Datos comunes para nombre único base
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_digits = ''.join(random.choices('0123456789', k=5))

    for idx, attachment in enumerate(file, start=1):
        if not attachment.datas or not attachment.name:
            raise ValidationError(f"Archivo adjunto inválido: {attachment.name}")

        file_ext = attachment.name.split('.')[-1].lower()
        if file_ext not in allowed_extensions:
            raise ValidationError(f"Tipo de archivo '{file_ext}' no permitido. Solo JPG/JPEG/MP4")

        # Nombre con numeración secuencial
        file_name = f"media_{timestamp}_{random_digits}-{idx}.{file_ext}"

        # Subir archivo
        s3_client.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=base64.b64decode(attachment.datas),
        )

        # Guardar URL
        file_url = f"https://{bucket_name}.s3.us-east-2.amazonaws.com/{file_name}"
        uploaded_urls.append(file_url)

    return uploaded_urls
