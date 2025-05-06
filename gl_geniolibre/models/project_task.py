# -*- coding: utf-8 -*-:

import requests
import base64  # Import the base64 module
import boto3
import time
import json

from datetime import datetime, timedelta
from odoo.exceptions import ValidationError
from odoo.tools import html2plaintext
from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


def show_notification(message=None, notif_type=None):
    action = {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'message': message if message else 'Default message',
            'type': notif_type if notif_type else 'warning',
            'next': {'type': 'ir.actions.act_window_close'},
        }
    }
    return action


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
                {'name': 'Facebook'},
                # {'name': 'Twitter'},
                {'name': 'Instagram'},
                # {'name': 'LinkedIn'},
                # {'name': 'YouTube'},
                {'name': 'TikTok'},
            ])
        return res


class project_task(models.Model):
    _inherit = "project.task"
    fecha_publicacion = fields.Datetime("Fecha y hora de Publicación", tracking=True,
                                        default=lambda self: fields.Datetime.now())
    inicio_promocion = fields.Date("Inicio de Promoción", tracking=True)
    fin_promocion = fields.Date("Fin de Promoción", tracking=True)
    presupuesto = fields.Monetary("Presupuesto", currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Moneda')
    adjuntos_ids = fields.Many2many('ir.attachment', string='Archivos Adjuntos', tracking=True)
    tipo = fields.Selection(
        selection=[('feed', 'Feed'), ('video_stories', 'Historia'),
                   ('video_reels', 'Reel'), ('otro', 'Otro')],
        string='Tipo de Publicación', default='otro', required=True)

    red_social_ids = fields.Many2many(
        'red.social',
        string='Redes Sociales',
    )

    hashtags=fields.Text(string="Hashtags")
    texto_en_diseno = fields.Html(string="Texto en diseño")

    partner_id = fields.Many2one('res.partner')

    partner_page_access_token = fields.Char(related="partner_id.facebook_page_access_token")
    partner_facebook_page_id = fields.Char(related="partner_id.facebook_page_id")
    partner_instagram_page_id = fields.Char(related="partner_id.instagram_page_id")
    partner_tiktok_access_token = fields.Char(related="partner_id.tiktok_access_token")

    post_estado = fields.Char(string="FB Status", default="Pendiente")
    fb_post_id = fields.Char(string="Facebook Post ID")
    fb_post_url = fields.Char(string="Facebook Post URL")
    fb_video_id = fields.Char(string="Facebook Video ID")
    fb_video_url = fields.Char(string="Facebook Video URL")
    inst_post_id = fields.Char(string="Instagram Post ID")
    inst_post_url = fields.Char(string="Instagram Post URL")
    tiktok_post_id = fields.Char(string="TikTok Post ID")
    tiktok_post_url = fields.Char(string="TikTok Post URL")

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
                if current_tipo in ["historia_video", "reels"]:
                    for attachment in current_attachments:
                        if attachment.mimetype != "video/mp4":
                            raise ValidationError(
                                "Solo se aceptan videos en formato MP4 para este tipo de publicación.")
                if current_tipo == "historia_image":
                    for attachment in current_attachments:
                        if attachment.mimetype != "image/jpeg":
                            raise ValidationError(
                                "Solo se aceptan imagenes en formato jpeg para este tipo de publicación.")
            else:
                for attachment in current_attachments:
                    if attachment.mimetype == "video/mp4":
                        raise ValidationError("Solo se aceptan imágenes para publicaciones de tipo 'Feed'.")

        # Proceed with normal save operation
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

    def revisar_post(self):
        error_message = []

        # Get Facebook Permalink
        if self.fb_post_id:
            if not self.fb_post_url: self.fb_post_url= 'https://www.facebook.com/' + self.fb_post_id

        # Get Instagram Permalink
        if self.inst_post_id:
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
        if self.tiktok_post_id:
            if not self.tiktok_post_url:
                error_message = []
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
                else:
                    status_data = response.json()
                    video_id = status_data.get("data", {}).get("publicaly_available_post_id")
                    if not video_id:
                        error_message.append("No se pudo obtener el video_id para esta publicación.")

                # Paso2: Obtener el permalink del video
                    # Campos a solicitar
                    # 2. Limpiar el video_id (por si viene con corchetes o espacios)
                    video_id=str(video_id)
                    video_id = video_id.strip("[]")
                       # 3. Construir solicitud
                    url = "https://open.tiktokapis.com/v2/video/query/"
                    headers = {
                        'Authorization': f'Bearer {self.partner_tiktok_access_token}',
                        'Content-Type': 'application/json'
                    }
                    params = {'fields': "share_url"}
                    payload = {
                        "filters": {
                            "video_ids": [str(video_id)]
                        }
                    }

                    # 4. Enviar y procesar respuesta
                    response = requests.post(
                        url,
                        headers=headers,
                        params=params,
                        json=payload,
                        timeout=10
                    )
                    if response.status_code == 200:
                        # Extraer el permalink
                        video_data = response.json().get('data', {}).get('videos', [])
                        if video_data:
                            self.tiktok_post_url = video_data[0].get('share_url')

                    else:
                        error = response.json().get('error', {})
                        error_message.append(f"Error TikTok API: {error.get('message')}")
                        return None

        # Notificaciones
        if error_message:
            show_notification(error_message, "warning")
        else:
            show_notification("Las URL de las publicaciones fueron actualizadas", "success")

        # Notificaciones
        if error_message:
            show_notification(error_message, "warning")
        else:
            show_notification("Las URL de las publicaciones fueron actualizadas", "success")

    def publicar_post(self):
        if self.state != "03_approved":
            raise ValidationError("El estado de la Tarea debe ser 'Aprobado'")

        show_notification("Debe seleccionar una red social", "warning")
        if not self.red_social_ids:
            raise ValidationError("Debe seleccionar al menos una red social")

        BASE_URL = 'https://graph.facebook.com/v22.0'

        # Get AWS and Facebook credentials
        parametros = self.env['ir.config_parameter'].sudo()
        aws_api = parametros.get_param('gl_aws.api_key')
        aws_secret = parametros.get_param('gl_aws.secret')
        user_access_token = parametros.get_param('gl_facebook.api_key')

        plain_description = html2plaintext(self.description or '')
        plain_hashtags = html2plaintext(self.hashtags or '')

        # Normalizar saltos de línea y asegurar doble espacio entre párrafos
        paragraphs = [p.strip() for p in plain_description.split('\n') if p.strip()]
        formatted_description = '\n\n'.join(paragraphs)

        combined_text = f"{formatted_description}\n\n{plain_hashtags}"
        # Funciones
        def upload_images_to_facebook():
            """
            Helper function to upload an image to Facebook.
            """

            image_bytes = base64.b64decode(self.adjuntos_ids.datas)
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
                raise ValidationError(f"Error al subir una imagen en Facebook: {response_upload.json()}")

        def publish_on_facebook(media_ids):


            url = f"{BASE_URL}/{self.partner_facebook_page_id}/{self.tipo}"
            if self.tipo == "feed":
                params = {
                    'access_token': self.partner_page_access_token,
                    'message': combined_text,
                    'attached_media': str([{'media_fbid': media_id} for media_id in media_ids]),
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
                    return response_data.get("post_id")
                else:
                    raise ValidationError(f"Error al publicar Reel en Facebook: {response_data}")

        def publish_on_instagram(media_urls):

            container_id = ""
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
                            'media_type': 'REELS'
                        }

                container_response = requests.post(container_url, params=container_params)
                container_id = container_response.json().get('id')
                if container_response.status_code != 200:
                    error_message = container_response.json()
                    raise ValidationError(f"Error al crear el contenedor de Instagram: {error_message}")

                # 2. Check processing status
                status_url = f"https://graph.facebook.com/v22.0/{container_id}"
                status_params = {
                    "access_token": self.partner_page_access_token,
                    "fields": "status_code"
                }

                for _ in range(30):
                    status_response = requests.get(status_url, params=status_params)
                    status_data = status_response.json()
                    if status_data.get('status_code') == 'FINISHED':
                        break  # Video is ready
                    elif status_data.get('status_code') == 'ERROR':
                        raise Exception("Video processing failed")

                    time.sleep(5)  # Wait 5 seconds between checks
                else:
                    raise Exception("Video processing timed out")
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

        # Validaciones
        if not self.partner_facebook_page_id and 'Facebook' in self.red_social_ids.mapped('name'):
            raise ValidationError("Los datos de acceso a Facebook no fueron configurados")

        if not self.partner_instagram_page_id and 'Instagram' in self.red_social_ids.mapped('name'):
            raise ValidationError("Los datos de acceso a Instagram no fueron configurados")

        if not self.partner_instagram_page_id and 'TikTok' in self.red_social_ids.mapped('name'):
            raise ValidationError("Los datos de acceso a TikTok no fueron configurados")

        # Publicaciones
        media_ids = []
        media_urls = upload_files_to_s3(self.adjuntos_ids, aws_api, aws_secret)

        # Publicar en Facebook

        if 'Facebook' in self.red_social_ids.mapped('name'):
            if self.tipo == "feed":
                for attachment in self.adjuntos_ids:
                    media_id = upload_images_to_facebook()
                    media_ids.append(media_id)
                fb_response = publish_on_facebook(media_ids)
            else:
                fb_response = publish_on_facebook(media_urls)

            if fb_response:
                self.write({
                    'fb_post_id': fb_response,
                    'fb_post_url': 'https://www.facebook.com/' + fb_response,
                })
            else:
                raise ValidationError(
                    f"Error al publicar en facebook: {fb_response}"
                )
        # Publicar en Instagram
        if 'Instagram' in self.red_social_ids.mapped('name'):
            ins_response = publish_on_instagram(media_urls)
            if ins_response:
                self.write({
                    'inst_post_id': ins_response,
                })
            else:
                raise ValidationError(
                    f"Error al publicar en Instagram: {ins_response}"
                )
        #
        # Publicar en TikTok
        if 'TikTok' in self.red_social_ids.mapped('name'):
            if self.partner_tiktok_access_token and self.tipo == "video_reels":
                tik_response = publish_on_tiktok(media_urls)
                if tik_response:
                    self.write({
                        'tiktok_post_id': tik_response,
                    })
                else:
                    raise ValidationError(
                        f"Error al publicar en Instagram: {tik_response}"
                    )
        self.write({
            'post_estado': 'Publicado',
        })
        return {
            'effect': {
                'message': 'The content was published',
                'fadeout': 'slow', 'type': 'rainbow_man', 'next': {'type': 'ir.actions.act_window_close'},
            }
        }


def upload_files_to_s3(file, aws_api, aws_secret):
    """
    Upload files to an AWS S3 bucket.

    Args:
        file (list): List of attachments (Odoo many2many field).
        aws_api (str): AWS access key ID.
        aws_secret (str): AWS secret access key.

    Returns:
        str: URL of the uploaded file.

    Raises:
        ValidationError: If no attachments are found, or if an error occurs during upload.
    """
    # AWS S3 configuration
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

    # Validate if there are any attachments
    if not file:
        raise ValidationError("No se encontraron archivos adjuntos.")

    allowed_extensions = {'jpg', 'jpeg', 'mp4'}
    uploaded_urls = []

    # Iterate over each attachment in the many2many field
    for attachment in file:
        try:
            # Validate attachment
            if not attachment.datas or not attachment.name:
                raise ValidationError(f"Archivo adjunto inválido: {attachment.name}")

            # Get file extension properly
            file_ext = attachment.name.split('.')[-1].lower()
            if file_ext not in allowed_extensions:
                raise ValidationError(
                    f"Tipo de archivo '{file_ext}' no permitido. Solo JPG/JPEG/MP4"
                )

            # Generate unique filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"media_{timestamp}.{file_ext}"

            # Upload to S3
            s3_client.put_object(
                Bucket=bucket_name,
                Key=file_name,
                Body=base64.b64decode(attachment.datas),
            )

            # Store URL
            file_url = f"https://{bucket_name}.s3.us-east-2.amazonaws.com/{file_name}"
            uploaded_urls.append(file_url)

        except Exception as e:
            raise ValidationError(f"Error al subir {attachment.name}: {str(e)}")
    return uploaded_urls


def delete_files_in_s3(media_urls, aws_api, aws_secret):
    return "Done"


def cron_job_publish_story():
    return "Done"
