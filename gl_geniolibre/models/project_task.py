# -*- coding: utf-8 -*-:
import random, re, requests, base64, boto3, logging
import subprocess
import json
import tempfile
import base64
import botocore

from io import BytesIO
from odoo.tools import html2plaintext
from odoo import models, fields, api
from datetime import datetime
from odoo.exceptions import ValidationError

import mimetypes

_logger = logging.getLogger(__name__)

API_VERSION = None
LinkedIn_Version = "202505"
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB recomendado para vídeos


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
    state = fields.Selection(tracking=True)  # track_visibility en versiones antiguas
    tag_ids = fields.Many2many(tracking=True)
    user_ids = fields.Many2many(tracking=True)

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
    texto_en_diseno = fields.Text(string="Texto en diseño")
    objetivo = fields.Text(string="Objetivo del post")

    partner_id = fields.Many2one('res.partner')
    partner_page_access_token = fields.Char(related="partner_id.facebook_page_access_token")
    partner_facebook_page_id = fields.Char(related="partner_id.facebook_page_id")
    partner_instagram_page_id = fields.Char(related="partner_id.instagram_page_id")
    partner_tiktok_access_token = fields.Char(related="partner_id.tiktok_access_token")
    partner_linkedin_page_id = fields.Char(related="partner_id.id_linkedin_organization")

    post_estado = fields.Char(string="Estado de la Publicación", default="Pendiente")
    fb_post_id = fields.Char(string="Facebook Post ID")
    fb_post_url = fields.Char(string="Facebook URL")
    fb_video_id = fields.Char(string="Facebook Video ID")  # ------ Este se elimina
    fb_video_url = fields.Char(string="Facebook Video URL")  # ------ Este se elimina
    inst_post_id = fields.Char(string="Instagram Post ID")
    inst_post_url = fields.Char(string="Instagram URL")
    linkedin_post_id = fields.Char(string="LinkedIn Post ID")
    linkedin_post_url = fields.Char(string="LinkedIn URL")
    tiktok_post_id = fields.Char(string="TikTok Post ID")
    tiktok_post_url = fields.Char(string="TikTok URL")

    # ====================================================================================== Tiktok Requisitos#
    # PRIVACIDAD (obligatorio por API)
    tiktok_privacy_level = fields.Selection([
        ('PUBLIC', 'Público'),
        ('FRIENDS', 'Amigos'),
        ('SELF_ONLY', 'Solo yo'),
    ], string="Privacidad TikTok", required=True, default='PUBLIC')

    # INTERACCIONES
    tiktok_allow_comments = fields.Boolean(string="Permitir comentarios", default=True)
    tiktok_allow_duet = fields.Boolean(string="Permitir duet", default=True)
    tiktok_allow_stitch = fields.Boolean(string="Permitir stitch", default=True)

    # TOGGLE PRINCIPAL (off por defecto según TikTok)
    tiktok_is_commercial = fields.Boolean(string="¿Es contenido comercial?", default=False, help="Indica si este contenido promociona una marca, producto o servicio")

    # OPCIONES MÚLTIPLES (Your Brand y Branded Content)
    tiktok_commercial_your_brand = fields.Boolean(string="Your Brand", help="Estás promocionando tu propia marca o negocio")
    tiktok_commercial_branded = fields.Boolean(string="Branded Content", help="Estás promocionando otra marca o tercero")
    tiktok_commercial_label_info = fields.Char(string="Etiqueta Comercial", readonly=True, help="Información sobre cómo se etiquetará el contenido")
    tiktok_privacy_note = fields.Char(string="Nota Privacidad", readonly=True, help="Información sobre restricciones de privacidad")
    tiktok_legal_text = fields.Char(string="Texto Legal", readonly=True, help="Texto de conformidad legal requerido por TikTok")

    # Traer los campos del partner (solo lectura)
    tiktok_nickname = fields.Char(related='partner_id.tiktok_nickname', string='TikTok Nickname', readonly=True, store=False)
    tiktok_avatar_url = fields.Char(related='partner_id.tiktok_avatar_url', string='TikTok Avatar URL', readonly=True, store=False)

    # Nuevo campo label para mensajes legales / restricciones de TikTok
    tiktok_creator_status_info = fields.Text(string="Estado del Creador (TikTok)", readonly=True, )
    tiktok_video_duration = fields.Integer(string="Duración del video (segundos)")

    @api.onchange('red_social_ids')
    def _onchange_red_social_ids_check_tiktok(self):
        """Ejecutar la validación SOLO si el usuario selecciona TikTok dentro de la lista."""
        if not self.red_social_ids:
            return

        # Normalizamos a string (ejemeplo: campos name)
        selected_networks = self.red_social_ids.mapped('name')

        # Si TikTok está seleccionado, ejecutamos validación
        if 'TikTok' in selected_networks:
            self.check_tiktok_creator_status()

    def unlink(self):
        for task in self:
            if task.tag_ids.filtered(lambda tag: tag.name.lower() == 'plantilla'):
                raise ValidationError('No puedes eliminar tareas con la etiqueta "Plantilla".')
        return super(project_task, self).unlink()

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
                            else:
                                try:
                                    duration_seconds = get_video_duration_ffprobe(attachment.datas)
                                    vals['tiktok_video_duration'] = duration_seconds
                                except Exception as e:
                                    raise ValidationError(f"No se pudo analizar el video MP4: {e}")

                else:  # current_tipo == "feed"
                    for attachment in current_attachments:
                        if attachment.mimetype == "video/mp4":
                            raise ValidationError("Solo se aceptan imágenes para publicaciones de tipo 'Feed'. No se permiten videos MP4.")
        return super().write(vals)

    def programar_post(self):
        try:
            self.ensure_one()  # Asegurar que operamos sobre un único registro al principio

            if self.state != "03_approved":
                raise ValidationError("El estado de la Tarea debe ser 'Aprobado' para poder programar el post.")

            # Eliminar la siguiente línea: Odoo manejará el commit de la transacción.
            self.post_estado = "Programado"  # Opcional: Si este metodo se llama desde un botón y quieres dar feedback  # podrías devolver una acción de notificación, pero para la lógica del modelo  # simplemente cambiar el estado es suficiente.  # Mensaje simple

        except Exception as e:
            _logger.error("Error en mi_funcion_critica: %s", e)
            # Correo
            error_detalle = str(e)
            self.env['mail.mail'].create({

                'subject': 'SERVER GL - Error en el Sistema',
                'body_html': f"""
                    <p><strong>Ocurrió un error en la automatización</strong></p>
                    <p><b>Proceso:</b> programar_post</p>
                    <p><b>Tarea:</b> {self.display_name}</p>
                    <p><b>ID:</b> {self.id}</p>
                    <p><b>Error:</b></p>
                    <pre style="background:#f6f6f6;padding:10px;border:1px solid #ddd;">{error_detalle}</pre>
                """,
                'email_to': self.env.ref('base.user_admin').email,
            }).send()
            raise ValidationError("Ocurrió un error inesperado. Revisa la notificación.")

    def cancelar_post(self):
        self.ensure_one()  # Asegura que solo hay un registro seleccionado
        self.post_estado = "Pendiente"

    def revisar_post(self, from_cron=False):
        API_VERSION = self.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_version')
        base_url = f'https://graph.facebook.com/{API_VERSION}'
        error_messages = []

        # Preparación del texto
        plain_description = html2plaintext(self.description or '')
        plain_hashtags = html2plaintext(self.hashtags or '')
        paragraphs = [p.strip() for p in plain_description.split('\n') if p.strip()]
        formatted_description = '\n\n'.join(paragraphs)
        formatted_description = remove_duplicate_links(formatted_description).rstrip()
        combined_text = f"{formatted_description}\n\n{plain_hashtags}"
        combined_text = combined_text.replace('\u200b', '').replace('\t', '').strip()

        try:
            # =========================================================
            # VALIDACIÓN BASE
            # =========================================================
            if self.post_estado != "Procesando":
                return True if from_cron else {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Sin acciones",
                        "message": "El contenido no está en estado Procesando.",
                        "type": "info",
                    },
                }

            # =========================================================
            # 2) FACEBOOK FEED (FOTOS)
            # =========================================================
            if self.post_estado == "Procesando" and self.tipo == "feed" and self.fb_post_id and not self.fb_post_url:

                try:
                    media_ids = json.loads(self.fb_post_id)
                except Exception:
                    media_ids = None

                if media_ids:
                    fb_feed_url = f"{base_url}/{self.partner_facebook_page_id}/feed"

                    params = {
                        "access_token": self.partner_page_access_token,
                        "message": combined_text or "",
                        "attached_media": json.dumps([{
                            "media_fbid": mid
                        } for mid in media_ids]),
                        "published": True,
                    }

                    try:
                        resp = requests.post(fb_feed_url, params=params, timeout=20)
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as e:
                        self.post_estado = "Error"
                        raise ValidationError(f"Facebook Feed: error de comunicación con la API. Detalle: {e}")

                    if data.get("id"):
                        self.fb_post_id = data["id"]
                        self.post_estado = "Publicado"
                    else:
                        err = data.get("error", {})
                        if err.get("code") in (9007, 2207027):
                            if from_cron:
                                return True
                            return {
                                "type": "ir.actions.client",
                                "tag": "display_notification",
                                "params": {
                                    "title": "Procesando",
                                    "message": "Facebook aún está procesando las imágenes.",
                                    "type": "warning",
                                    "sticky": True,
                                    "next": {
                                        "type": "ir.actions.client",
                                        "tag": "reload",
                                    }
                                },
                            }

                        self.post_estado = "Error"
                        raise ValidationError(f"Facebook Feed: error al publicar. Detalle: {data}")

            # URL Facebook Feed
            if self.fb_post_id and self.post_estado == "Publicado" and not self.fb_post_url:
                self.fb_post_url = f"https://www.facebook.com/{self.fb_post_id}"

            # =========================================================
            # 2.2) FACEBOOK STORIES (VIDEO)
            # =========================================================
            if self.tipo == "video_stories" and self.fb_post_id and not self.fb_post_url:
                self.fb_post_url = f"https://www.facebook.com/{self.partner_facebook_page_id}"

                if from_cron:
                    return True

                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "URL actualizado",
                        "message": "Historia publicada. Enlace de Stories disponible.",
                        "type": "success",
                        "sticky": False,
                        "next": {
                            "type": "ir.actions.client",
                            "tag": "reload"
                        },
                    },
                }

            # =========================================================
            # 3) FACEBOOK REELS (VIDEO) – MISMO PATRÓN QUE FEED
            # =========================================================
            if self.tipo == "video_reels" and self.fb_post_id and not self.fb_post_url:
                # 3.1 Consultar estado del video
                status_url = f"{base_url}/{self.fb_post_id}"
                status_params = {
                    "access_token": self.partner_page_access_token,
                    "fields": "status",
                }
                try:
                    resp = requests.get(status_url, params=status_params, timeout=20)
                    resp.raise_for_status()
                    sdata = resp.json()
                    print(sdata)
                except Exception as e:
                    self.post_estado = "Error"
                    raise ValidationError(f"Facebook Reel: no se pudo consultar el estado del video. Detalle: {e}")

                video_status = (sdata.get("status") or {}).get("video_status")

                # Error de procesamiento
                if video_status == "error":
                    self.post_estado = "Error"
                    raise ValidationError(f"Facebook Reel: error procesando el video. Detalle: {sdata}")

                # 3.2 Publicar Reel
                if video_status in ("upload_complete", "processing"):

                    publish_url = f"{base_url}/{self.partner_facebook_page_id}/video_reels"
                    publish_params = {
                        "access_token": self.partner_page_access_token,
                        "video_id": self.fb_post_id,
                        "upload_phase": "finish",
                        "video_state": "PUBLISHED",
                        "description": combined_text or "",
                    }
                    try:
                        print(publish_params)

                        resp = requests.post(publish_url, params=publish_params, timeout=20)
                        resp.raise_for_status()
                        pdata = resp.json()

                        # Subir thumbnail al video (best-effort)
                        if self.imagen_portada and self.tipo == "video_reels":
                            image_data = base64.b64decode(self.imagen_portada)
                            image_file = BytesIO(image_data)
                            image_file.name = 'miniatura.jpg'  # necesario para multipart/form-data

                            url = f"https://graph.facebook.com/{API_VERSION}/{self.fb_post_id}/thumbnails"
                            files = {
                                'source': ('miniatura.jpg', image_file, 'image/jpeg')
                            }
                            data = {
                                'access_token': self.partner_page_access_token,
                                'is_preferred': 'true'
                            }
                            response = requests.post(url, files=files, data=data)
                            print("thumbnails", response)

                        print("success", pdata.get("post_id"))

                        if "post_id" in pdata:
                            self.fb_post_id = pdata["post_id"]
                        else:
                            raise ValidationError(f"Facebook Reel: no devolvió post_id. Detalle: {pdata}")

                        # 3.3 Obtener URL del Reel (YA ES POST REAL)
                        try:
                            r = requests.get(f"{base_url}/{self.fb_post_id}", params={
                                "fields": "permalink_url",
                                "access_token": self.partner_page_access_token,
                            }, timeout=20, )
                            r.raise_for_status()

                            permalink = r.json().get("permalink_url")
                            if permalink:
                                # Facebook ya devuelve URL completa
                                self.fb_post_url = permalink

                        except Exception as e:
                            raise ValidationError(f"Error al obtener permalink del Reel: {e}")

                    except Exception as e:
                        raise ValidationError(f"Error al publicar Reel en Facebook: {e}")

                    # Facebook dice: aún procesando → NO es error
                    err = pdata.get("error")
                    if err and err.get("code") in (9007, 2207027):
                        if from_cron:
                            return True
                        return {
                            "type": "ir.actions.client",
                            "tag": "display_notification",
                            "params": {
                                "title": "Procesando",
                                "message": "Facebook aún está procesando el reel.",
                                "type": "warning",
                                "sticky": True,
                            },
                        }

                    # Error real
                    if "post_id" not in pdata:

                        raise ValidationError(f"Facebook Reel: fallo al publicar. Detalle: {pdata}")

                    # Éxito → ya publicado
                    self.fb_post_id = pdata["post_id"]



            # =========================================================
            # 4) TIKTOK
            # =========================================================
            # if self.tiktok_post_id and not self.tiktok_post_url:
            #     status_url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
            #     headers = {
            #         "Authorization": f"Bearer {self.partner_tiktok_access_token}",
            #         "Content-Type": "application/json",
            #     }
            #     payload = {
            #         "publish_id": self.tiktok_post_id
            #     }
            #     data = requests.post(status_url, headers=headers, json=payload).json()
            #
            #     if data.get("data", {}).get("status") == "PUBLISH_COMPLETE":
            #         video_id = data["data"].get("publicaly_available_post_id")
            #         if video_id:
            #             self.tiktok_post_url = f"https://www.tiktok.com/@_/video/{video_id}"

            # =========================================================
            # 5) LINKEDIN
            # =========================================================
            # if self.linkedin_post_id and not self.linkedin_post_url:
            #     self.linkedin_post_url = f"https://www.linkedin.com/feed/update/{self.linkedin_post_id}/"

            # =========================================================
            # 6) ESTADO FINAL
            # =========================================================
            # if error_messages:
            #     self.post_estado = "Error"
            # elif self.fb_post_url or self.inst_post_url or self.tiktok_post_url or self.linkedin_post_url:
            #     self.post_estado = "Publicado"
            # return {
            #     'effect': {
            #         'message': f"Contenido publicado exitosamente",
            #         'fadeout': 'slow',
            #         'type': 'rainbow_man',
            #         'next': {
            #             'type': 'ir.actions.act_window_close'
            #         },
            #     }
            # }



        except Exception as e:
            _logger.error("Error en revisar_post (%s): %s", self.id, e)

            if from_cron:
                raise

            # self.post_estado = "Error"

            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Error inesperado",
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                },
            }

    def publicar_post(self):
        API_VERSION = self.env['ir.config_parameter'].sudo().get_param('gl_facebook.api_version')
        BASE_URL = f'https://graph.facebook.com/{API_VERSION}'

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

        def publish_on_facebook(media_urls, combined_text):
            """
            SIEMPRE pendiente.
            - feed (fotos/carrusel): guarda JSON de media_fbid en fb_post_id (temporal)
            - video/reels: sube video y guarda fb_video_id
            """
            BASE_URL_LOCAL = f'https://graph.facebook.com/{API_VERSION}'

            # ---- FEED (FOTOS) ----
            if self.tipo == "feed":

                photo_ids = []

                for photo_url in media_urls:
                    upload_url = f"{BASE_URL_LOCAL}/{self.partner_facebook_page_id}/photos"
                    params = {
                        "url": photo_url,  # URL pública (S3)
                        "published": "false",  # CLAVE
                        "access_token": self.partner_page_access_token,
                    }
                    resp = requests.post(upload_url, params=params)
                    data = resp.json()
                    if "id" not in data:
                        raise ValidationError(f"Error subiendo foto: {data}")

                    photo_ids.append(data["id"])

                # Guardamos SOLO IDs reales de Facebook
                self.write({
                    "fb_post_id": json.dumps(photo_ids),  # ["photo_id1","photo_id2",...]
                    "fb_post_url": False,
                    "post_estado": "Procesando",
                })

                return True

            # =====================================================
            # 2) FACEBOOK STORIES (VIDEO) → PUBLICACIÓN DIRECTA
            # =====================================================
            if self.tipo == "video_stories":

                url = f"{BASE_URL_LOCAL}/{self.partner_facebook_page_id}/video_stories"

                # 1) start
                params = {
                    "upload_phase": "start",
                    "access_token": self.partner_page_access_token,
                }
                resp = requests.post(url, params=params)
                data = resp.json()

                if "video_id" not in data or "upload_url" not in data:
                    raise ValidationError(f"Error iniciando upload Story FB: {data}")

                video_id = data["video_id"]
                upload_url = data["upload_url"]

                # Guardamos ID del video story
                self.write({
                    "fb_post_id": video_id,
                    "post_estado": "Procesando",
                })

                # 2) upload file
                headers = {
                    "Authorization": f"OAuth {self.partner_page_access_token}",
                    "file_url": media_urls[0],  # URL pública del video en S3
                }
                up = requests.post(upload_url, headers=headers)
                up_data = up.json()

                if "success" not in up_data:
                    raise ValidationError(f"Error subiendo video Story FB: {up_data}")

                # 3) finish (requiere video_id)
                finish_params = {
                    "upload_phase": "finish",
                    "access_token": self.partner_page_access_token,
                    "video_id": video_id,  # <-- CLAVE
                }

                fin = requests.post(url, params=finish_params)  # url = /{page_id}/video_stories
                fin_data = fin.json()

                # IMPORTANTE: si Facebook devuelve post_id, guárdalo para armar URL luego
                if fin_data.get("post_id"):
                    self.write({
                        "fb_post_id": fin_data["post_id"]
                    })
                return True

            # =====================================================
            # 3) FACEBOOK REELS (VIDEO)
            # =====================================================
            if self.tipo == "video_reels":

                url = f"{BASE_URL_LOCAL}/{self.partner_facebook_page_id}/video_reels"

                # 1) start upload session
                params = {
                    "upload_phase": "start",
                    "access_token": self.partner_page_access_token,
                }
                resp = requests.post(url, params=params)
                data = resp.json()

                if "video_id" not in data or "upload_url" not in data:
                    raise ValidationError(f"Error Starting session (Reel FB): {data}")

                video_id = data["video_id"]
                upload_url = data["upload_url"]

                # Guardamos TEMPORALMENTE video_id en fb_post_id
                self.write({
                    "fb_post_id": video_id,  # temporal (video_id)
                    "fb_post_url": False,
                    "post_estado": "Procesando",
                })

                # 2) upload file via file_url
                headers = {
                    "Authorization": f"OAuth {self.partner_page_access_token}",
                    "file_url": media_urls[0],  # URL pública en S3
                }
                up = requests.post(upload_url, headers=headers)
                up_data = up.json()

                if "success" not in up_data:
                    raise ValidationError(f"Error uploading Reel FB: {up_data}")

                # 3) finish upload SIN publicar
                finish_url = f"{BASE_URL_LOCAL}/{video_id}"
                finish_params = {
                    "access_token": self.partner_page_access_token,
                    "upload_phase": "finish",
                    "video_state": "UNPUBLISHED",
                    "description": combined_text,
                }

                fin = requests.post(finish_url, params=finish_params)
                fin_data = fin.json()

                if fin.status_code != 200:
                    raise ValidationError(f"Error finishing upload Reel FB: {fin_data}")

                return True
            return None

        def publish_on_instagram(media_urls, combined_text, cover_url=None):
            """
            SIEMPRE pendiente.
            Crea container (inst_post_id) y NO hace media_publish aquí.
            """
            BASE_URL_LOCAL = f'https://graph.facebook.com/{API_VERSION}'
            container_url = f"{BASE_URL_LOCAL}/{self.partner_instagram_page_id}/media"
            carousel_ids = []

            if len(media_urls) == 1:
                if self.tipo == "feed":
                    container_params = {
                        'access_token': self.partner_page_access_token,
                        'caption': combined_text,
                        'image_url': media_urls[0],
                        'published': False,
                    }
                else:
                    if self.tipo == "video_stories":
                        container_params = {
                            'access_token': self.partner_page_access_token,
                            'caption': combined_text,
                            'video_url': media_urls[0],
                            'published': False,
                            'media_type': 'STORIES'
                        }
                    else:
                        container_params = {
                            'access_token': self.partner_page_access_token,
                            'caption': combined_text,
                            'video_url': media_urls[0],
                            'published': False,
                            'media_type': 'REELS',
                            'cover_url': cover_url
                        }

                r = requests.post(container_url, params=container_params)
                data = r.json()
                if r.status_code != 200 or not data.get("id"):
                    raise ValidationError(f"Error al crear contenedor IG: {data}")
                container_id = data["id"]

            else:
                for url in media_urls:
                    item_params = {
                        'access_token': self.partner_page_access_token,
                        'is_carousel_item': 'true',
                        'image_url': url,
                        'published': False,
                    }
                    rr = requests.post(container_url, params=item_params)
                    d = rr.json()
                    if rr.status_code != 200 or not d.get("id"):
                        raise ValidationError(f"Error item carrusel IG: {d}")
                    carousel_ids.append(d["id"])

                carousel_params = {
                    'media_type': 'CAROUSEL',
                    'children': ",".join(carousel_ids),
                    'caption': combined_text,
                    'access_token': self.partner_page_access_token,
                    'published': False,
                }
                r = requests.post(container_url, params=carousel_params)
                data = r.json()
                if r.status_code != 200 or not data.get("id"):
                    raise ValidationError(f"Error contenedor carrusel IG: {data}")
                container_id = data["id"]

            self.write({
                "inst_post_id": container_id,
                "inst_post_url": False,
                "post_estado": "Procesando",
            })

            print("Fin Publicar en Instagram", container_id)

            return True

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

            self.ensure_one()

            # -------------------------------------------------- Validaciones básicas
            if not media_urls:
                raise ValidationError("No se proporcionaron URLs de medios")

            linkedin_access_token = (self.env["ir.config_parameter"].sudo().get_param("linkedin.access_token"))
            if not linkedin_access_token:
                raise ValidationError("Falta configurar linkedin.access_token")

            org_urn = f"urn:li:organization:{self.partner_linkedin_page_id}"
            headers = {
                "Authorization": f"Bearer {linkedin_access_token}",
                "LinkedIn-Version": LinkedIn_Version,
                "X-RestLi-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }
            session = requests.Session()
            session.headers.update(headers)

            # Combinar título y descripción

            try:
                # ================================================= VIDEO (reel) ====
                if self.tipo == "video_reels":
                    if len(media_urls) != 1:
                        raise ValidationError("Los Reels solo admiten un (1) video")

                    # 1‑A  initializeUpload
                    head_resp = requests.head(media_urls[0])
                    head_resp.raise_for_status()
                    size_bytes = int(head_resp.headers.get("Content-Length", 0))
                    if size_bytes == 0:
                        raise ValidationError("No se pudo obtener el tamaño del video")

                    # ¿Tenemos portada?
                    has_thumbnail = bool(self.imagen_portada)

                    init_payload = {
                        "initializeUploadRequest": {
                            "owner": org_urn,
                            "fileSizeBytes": size_bytes,
                            "uploadCaptions": False,
                            "uploadThumbnail": has_thumbnail  # ▶️ TRUE solo si hay portada
                        }
                    }

                    init_resp = session.post("https://api.linkedin.com/rest/videos?action=initializeUpload", json=init_payload)

                    init_resp.raise_for_status()
                    init_json = init_resp.json()

                    video_urn = init_json["value"]["video"]
                    upload_token = init_json["value"]["uploadToken"]
                    upload_instructions = init_json["value"]["uploadInstructions"]
                    thumbnail_url = init_json["value"].get("thumbnailUploadUrl")  # ← solo si pedimos thumbnail

                    uploaded_etags = []
                    for instruction in upload_instructions:
                        upload_url = instruction["uploadUrl"]
                        first_byte = instruction["firstByte"]
                        last_byte = instruction["lastByte"]
                        chunk_size = last_byte - first_byte + 1
                        range_header = f"bytes={first_byte}-{last_byte}"

                        # Descargar el chunk exacto
                        chunk_resp = requests.get(media_urls[0], headers={
                            "Range": range_header
                        }, stream=True)

                        chunk_resp.raise_for_status()
                        chunk_data = chunk_resp.content  # Leer contenido completo

                        put_headers = {
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(chunk_size)
                        }

                        # Subir a LinkedIn
                        upload_resp = session.put(upload_url, headers=put_headers, data=chunk_data, timeout=30)
                        upload_resp.raise_for_status()

                        etag = upload_resp.headers.get("ETag")
                        if not etag:
                            raise ValidationError("No se recibió ETag al subir parte del video")
                        uploaded_etags.append(etag)

                        # ------------------------------------------------------------------ 1‑C  subir la miniatura (si existe)

                    if has_thumbnail and thumbnail_url:
                        thumb_bytes = base64.b64decode(self.imagen_portada)
                        session.put(thumbnail_url, headers={
                            "Content-Type": "image/jpeg"
                        },  # fijo, siempre JPG
                                    data=thumb_bytes, timeout=15, ).raise_for_status()

                    # 1‑C Finalizar la subida
                    finalize_payload = {
                        "finalizeUploadRequest": {
                            "video": video_urn,
                            "uploadToken": upload_token,
                            "uploadedPartIds": uploaded_etags  # ❗ ETags, no partNumbers
                        }
                    }
                    finalize_resp = session.post("https://api.linkedin.com/rest/videos?action=finalizeUpload", json=finalize_payload)
                    finalize_resp.raise_for_status()

                    # Estado "procesando"
                    self.post_estado = "Procesando"
                    self.linkedin_post_id = video_urn

                    # 1‑D Crear el post (reel) usando el video_urn
                    post_data = {
                        "author": org_urn,
                        "commentary": combined_text,
                        "visibility": "PUBLIC",
                        "distribution": {
                            "feedDistribution": "MAIN_FEED",
                            "targetEntities": [],
                            "thirdPartyDistributionChannels": [],
                        },
                        "content": {
                            "media": {
                                "id": video_urn,
                            }
                        },
                        "lifecycleState": "PUBLISHED",
                        "isReshareDisabledByAuthor": False,
                    }

                # =============================================== IMÁGENES / CARRUSEL
                elif self.tipo == "feed":
                    media_urns = []
                    for url in media_urls:
                        # 2‑A  initializeUpload por imagen
                        init_resp = session.post("https://api.linkedin.com/rest/images?action=initializeUpload", json={
                            "initializeUploadRequest": {
                                "owner": org_urn
                            }
                        })
                        init_resp.raise_for_status()
                        init_json = init_resp.json()

                        image_urn = init_json["value"]["image"]
                        upload_url = init_json["value"]["uploadUrl"]
                        mime, _ = mimetypes.guess_type(url)

                        # 2‑B  subir la imagen
                        img_content = requests.get(url).content
                        requests.put(upload_url, headers={
                            "Content-Type": mime or "application/octet-stream",
                        }, data=img_content).raise_for_status()
                        media_urns.append(image_urn)

                    # 2‑C  crear post según 1 o varias imágenes
                    post_data = {
                        "author": org_urn,
                        "commentary": combined_text,
                        "visibility": "PUBLIC",
                        "distribution": {
                            "feedDistribution": "MAIN_FEED",
                            "targetEntities": [],
                            "thirdPartyDistributionChannels": [],
                        },
                        "lifecycleState": "PUBLISHED",
                        "isReshareDisabledByAuthor": False,
                    }
                    if len(media_urns) == 1:
                        post_data["content"] = {
                            "media": {
                                "id": media_urns[0]
                            }
                        }
                    else:
                        post_data["content"] = {
                            "multiImage": {
                                "images": [{
                                    "id": u
                                } for u in media_urns]
                            }
                        }

                # ======================================================= Otros tipos
                else:
                    raise ValidationError(f"Tipo de publicación no soportado: {self.tipo}")

                # =============================================== 3) Crear el post
                post_resp = session.post("https://api.linkedin.com/rest/posts", json=post_data)

                post_resp.raise_for_status()

                post_urn = post_resp.headers.get("X-RestLi-Id")
                if not post_urn:
                    raise ValidationError("LinkedIn no devolvió un URN en X‑RestLi‑Id")

                # Solo si no es video, marcamos como publicado
                if self.tipo != "video_reels":
                    self.post_estado = "Publicado"

                return {
                    "post_id": post_urn,
                    "post_url": f"https://www.linkedin.com/feed/update/{post_urn}/"
                }

            # ---------------------------------------------------- Manejo de errores
            except requests.exceptions.HTTPError as err:
                self.post_estado = "error"
                error_msg = f"Error HTTP {err.response.status_code}"
                try:
                    error_details = err.response.json()
                    if 'message' in error_details:
                        error_msg += f": {error_details['message']}"
                    elif 'error' in error_details:
                        error_msg += f": {error_details['error']}"
                except:
                    error_msg += f": {err.response.text[:200]}"

                raise ValidationError(error_msg) from err

            except Exception as e:
                self.post_estado = "error"
                raise ValidationError(f"Error inesperado: {str(e)}") from e

        # Validaciones iniciales (detienen todo el proceso si fallan)
        if not self.imagen_portada and self.tipo == "video_reels":
            raise ValidationError("Debe especificar una portada para el reel")

        if not self.fecha_publicacion:
            raise ValidationError("Debe seleccionar una fecha de publicación")

        if self.state != "03_approved":
            raise ValidationError("El estado de la Tarea debe ser 'Aprobado'")

        if not self.red_social_ids:
            raise ValidationError("Debe seleccionar al menos una red social")

        try:
            # Configuración inicial
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
            _logger.info(f"Archivos subidos a S3. URLs obtenidas: {media_urls}")
            # Publicación en redes sociales con gestión de errores individual
            errors = []
            success_messages = []
            published_on = []

            if self.imagen_portada and self.tipo == "video_reels":
                cover_url = upload_files_to_s3([("portada.jpg", self.imagen_portada)], aws_api, aws_secret)[0]

            procesando = False
            # Facebook
            if 'Facebook' in self.red_social_ids.mapped('name'):
                try:
                    # if self.tipo == "feed":
                    #     for attachment in self.adjuntos_ids:
                    #         media_id = upload_images_to_facebook(attachment)
                    #         media_ids.append(media_id)
                    #     publish_on_facebook(media_ids, combined_text)  # <- ahora correcto
                    # else:
                    publish_on_facebook(media_urls, combined_text)  # <- ahora correcto
                    success_messages.append("Facebook: Publicación en proceso")
                    published_on.append("Facebook")
                except Exception as e:
                    errors.append(f"Facebook: {str(e)}")

            # Instagram
            if 'Instagram' in self.red_social_ids.mapped('name'):
                try:
                    cover_url = None
                    if self.imagen_portada and self.tipo == "video_reels":
                        cover_url = upload_files_to_s3([("portada.jpg", self.imagen_portada)], aws_api, aws_secret)[0]

                    publish_on_instagram(media_urls, combined_text, cover_url)

                    success_messages.append("Instagram: Publicación en proceso")
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
                            'linkedin_post_id': linkedin_response["post_id"],
                            'linkedin_post_url': linkedin_response["post_url"]
                        })
                        success_messages.append("LinkedIn: Publicación exitosa")
                        published_on.append("LinkedIn")
                    else:
                        errors.append("LinkedIn: No se recibió respuesta del servidor")
                except Exception as e:
                    errors.append(f"LinkedIn: {str(e)}")

            # Resultado final
            if published_on:
                # SIEMPRE queda en Procesando (la publicación real ocurre en revisar_post)
                self.write({
                    'post_estado': 'Procesando'
                })

                if errors:
                    # Publicación parcialmente exitosa
                    error_detalle = "\n".join(errors)
                    _logger.error("Error en publicar_post: %s", error_detalle)

                    self.env['mail.mail'].create({
                        'subject': 'SERVER GL - Error en el Sistema',
                        'body_html': f"""
                            <p><strong>Ocurrió un error en la automatización</strong></p>
                            <p><b>Proceso:</b> publicar_post</p>
                            <p><b>Tarea:</b> {self.display_name}</p>
                            <p><b>ID:</b> {self.id}</p>
                            <p><b>Error:</b></p>
                            <pre style="background:#f6f6f6;padding:10px;border:1px solid #ddd;">{error_detalle}</pre>
                        """,
                        'email_to': self.env.ref('base.user_admin').email,
                    }).send()

                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Proceso con observaciones",
                            "message": '\n'.join(success_messages + [
                                "Errores:"
                            ] + errors),
                            "type": "danger",
                            "sticky": True,
                        },
                    }

                else:
                    try:
                        self.revisar_post()
                    except Exception as err:
                        # No rompemos la UI, solo registramos
                        _logger.error("Error en revisar_post (post ID %s): %s", self.id, err)

                    return {
                        "type": "ir.actions.client",
                        "tag": "display_notification",
                        "params": {
                            "title": "Proceso en curso",
                            "message": f"Contenido enviado a procesamiento en: {', '.join(published_on)}",
                            "type": "success",
                            "sticky": False,
                            "next": {
                                "type": "ir.actions.client",
                                "tag": "reload",
                            }
                        },
                    }

            else:
                # Todo falló
                error_detalle = "\n".join(errors) if errors else "Error no especificado"
                _logger.error("Error en publicar_post: %s", error_detalle)

                self.write({
                    'post_estado': 'Procesando'
                })
                print("Aqui debe cebir Procesando")
                self.env['mail.mail'].create({
                    'subject': 'SERVER GL - Error en el Sistema',
                    'body_html': f"""
                        <p><strong>Ocurrió un error en la automatización</strong></p>
                        <p><b>Proceso:</b> publicar_post</p>
                        <p><b>Tarea:</b> {self.display_name}</p>
                        <p><b>ID:</b> {self.id}</p>
                        <p><b>Error:</b></p>
                        <pre style="background:#f6f6f6;padding:10px;border:1px solid #ddd;">{error_detalle}</pre>
                    """,
                    'email_to': self.env.ref('base.user_admin').email,
                }).send()

                raise ValidationError("No se pudo iniciar el proceso en ninguna red social:\n" + error_detalle)

        except Exception as e:
            _logger.error("Error en mi_funcion_critica: %s", e)
            error_detalle = str(e)
            self.env['mail.mail'].create({
                'subject': 'SERVER GL - Error en el Sistema',
                'body_html': f"""
                    <p><strong>Ocurrió un error en la automatización</strong></p>
                    <p><b>Proceso:</b> publicar_post</p>
                    <p><b>Tarea:</b> {self.display_name}</p>
                    <p><b>ID:</b> {self.id}</p>
                    <p><b>Error:</b></p>
                        <pre style="background:#f6f6f6;padding:10px;border:1px solid #ddd;">{error_detalle}</pre>
                    """,
                'email_to': self.env.ref('base.user_admin').email,
            }).send()
            raise ValidationError(f"Error en el proceso de publicación: {str(e)}")

    def check_tiktok_creator_status(self):
        self.ensure_one()

        # Token del creador (ajústalo a donde lo guardes)
        access_token = self.partner_id.tiktok_access_token
        if not access_token:
            raise ValidationError("No existe access_token de TikTok para este creador.")

        url = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "fields": [
                "can_publish",
                "max_video_post_duration_sec"
            ]
        }

        response = requests.post(url, json=payload, headers=headers, timeout=10)

        if response.status_code != 200:
            msg = f"Error consultando TikTok Creator Info: {response.text}"
            self.tiktok_creator_status_info = msg
            raise ValidationError(msg)

        data = response.json()

        # ----------------------------
        # 1) VERIFICAR SI PUEDE PUBLICAR
        # ----------------------------
        can_publish = data.get("data", {}).get("can_publish", None)

        if can_publish is False:
            msg = "❌ El creador ha alcanzado el límite de publicaciones. No puede publicar en este momento."
            self.tiktok_creator_status_info = msg
            raise ValidationError(msg)

        # ----------------------------
        # 2) VERIFICAR DURACIÓN PERMITIDA
        # ----------------------------
        max_duration = data.get("data", {}).get("max_video_post_duration_sec", None)

        if max_duration and self.tiktok_video_duration:
            if self.tiktok_video_duration > max_duration:
                msg = (f"⛔ El video excede la duración máxima permitida.\n"
                       f"Duración del video: {self.tiktok_video_duration} s\n"
                       f"Máximo permitido por TikTok: {max_duration} s")
                self.tiktok_creator_status_info = msg
                raise ValidationError(msg)

        # ----------------------------
        # SI TODO OK → MENSAJE POSITIVO
        # ----------------------------
        ok_msg = (f"✔ El creador puede publicar.\n"
                  f"Duración máxima permitida: {max_duration} segundos.\n"
                  f"Duración del video a publicar: {self.tiktok_video_duration} segundos.")
        self.tiktok_creator_status_info = ok_msg

        return True


def upload_files_to_s3(files, aws_api, aws_secret):
    """Sube archivos (imágenes o videos) a AWS S3 y devuelve sus URLs públicas."""
    aws_access_key_id = aws_api
    aws_secret_access_key = aws_secret
    bucket_name = 'odoo-geniolibre'
    region_name = 'us-east-2'

    _logger.info("AWS S3 configuración inicial")

    if not aws_access_key_id or not aws_secret_access_key:
        raise ValidationError("No se configuró correctamente el servicio de AWS.")

    # Crear cliente con timeout seguro
    try:
        _logger.info("Iniciando conexión con AWS S3...")
        s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key, region_name=region_name, config=botocore.config.Config(connect_timeout=5, read_timeout=15), )
        _logger.info("Cliente AWS S3 creado correctamente.")
    except Exception as e:
        _logger.exception("Error al crear el cliente AWS S3")
        raise ValidationError(f"Error al crear el cliente AWS S3: {e}")

    if not files:
        raise ValidationError("No se encontraron archivos adjuntos o imágenes.")

    # Normalizar a lista
    if hasattr(files, 'ids'):
        files = list(files)
    elif isinstance(files, (tuple, list)):
        files = list(files)
    else:
        files = [
            files
        ]

    allowed_extensions = {
        'jpg',
        'jpeg',
        'mp4'
    }
    uploaded_urls = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_digits = ''.join(random.choices('0123456789', k=5))

    for idx, item in enumerate(files, start=1):

        try:
            # Detectar tipo de objeto
            if hasattr(item, 'datas') and hasattr(item, 'name'):  # ir.attachment
                file_name_raw = item.name
                file_data = item.datas
            elif isinstance(item, (tuple, list)) and len(item) == 2:  # (name, data)
                file_name_raw, file_data = item
            elif isinstance(item, str):  # base64 string
                file_name_raw = f"upload_{timestamp}_{random_digits}-{idx}.jpg"
                file_data = item
            else:
                raise ValidationError("Formato de archivo no soportado o inválido.")

            file_ext = file_name_raw.split('.')[-1].lower()
            if file_ext not in allowed_extensions:
                raise ValidationError(f"Tipo de archivo '{file_ext}' no permitido. Solo JPG, JPEG o MP4.")

            file_name = f"media_{timestamp}_{random_digits}-{idx}.{file_ext}"
            _logger.info(f"Preparando archivo {file_name_raw} para subida ({file_ext})...")

            # Decodificar y subir
            file_bytes = base64.b64decode(file_data)
            _logger.info(f"Subiendo {file_name} ({len(file_bytes)} bytes) a S3...")

            s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=file_bytes, ContentType='image/jpeg' if file_ext in [
                'jpg',
                'jpeg'
            ] else 'video/mp4', )

            file_url = f"https://{bucket_name}.s3.{region_name}.amazonaws.com/{file_name}"
            uploaded_urls.append(file_url)

            _logger.info(f"Archivo subido correctamente: {file_url}")

        except Exception as e:
            _logger.exception(f"Error al subir {file_name_raw} a S3")
            raise ValidationError(f"Error al subir archivo {file_name_raw}: {str(e)}")

    _logger.info(f"Todos los archivos subidos correctamente. Total: {len(uploaded_urls)}")
    return uploaded_urls


def get_video_duration_ffprobe(base64_data):
    import subprocess, json, tempfile, base64
    from odoo.exceptions import ValidationError

    try:
        with tempfile.NamedTemporaryFile(delete=True, suffix=".mp4") as tmp:
            tmp.write(base64.b64decode(base64_data))
            tmp.flush()

            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                tmp.name
            ]

            # 🔥 timeout de 3 segundos → evita loops infinitos
            output = subprocess.check_output(cmd, timeout=3)
            info = json.loads(output.decode("utf-8"))

            duration = float(info["format"]["duration"])
            return int(duration)

    except subprocess.TimeoutExpired:
        raise ValidationError("ffprobe demoró demasiado y fue detenido. El archivo puede estar corrupto.")

    except Exception as e:
        raise ValidationError(f"No se pudo obtener la duración del video usando ffprobe: {e}")


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
