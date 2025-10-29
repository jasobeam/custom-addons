import json
from odoo import models, fields
from odoo.exceptions import ValidationError
import requests


class GeneradorContenidoPropuesta(models.Model):
    _name = "gl.contenido.propuesta"
    _description = "Propuesta de Contenido"

    flujo_id = fields.Many2one("gl.contenido.flujo", string="Flujo de Contenido", required=True, ondelete="cascade")
    nombre = fields.Char("Título de la Propuesta", required=True)
    copy = fields.Html("Copy / Texto")
    hashtags = fields.Char("Hashtags")
    aprobado = fields.Boolean("Aprobado", default=False)


class GeneradorContenidoFlujo(models.Model):
    _name = "gl.contenido.flujo"
    name = fields.Char(string="Nombre del Flujo", required=True, tracking=True, help="Nombre o título principal del flujo de contenido (ej. Campaña de Julio, Newport - Cursos de Manejo)")

    _description = "Flujo del Generador de Contenido"
    _inherit = [
        "mail.thread",
        "mail.activity.mixin"
    ]
    date_start = fields.Date(string="Fecha de Inicio", tracking=True, help="Fecha de inicio del rango de planificación o análisis.")
    date = fields.Date(string="Fecha de Fin", tracking=True, help="Fecha de fin del rango de planificación o análisis.")
    plan_cliente = fields.Char(string="Plan del Cliente", related="partner_id.plan_descripcion", readonly=True)
    plan_post = fields.Integer(string="Posts", related="partner_id.plan_post", readonly=True)
    plan_historia = fields.Integer(string="Historias", related="partner_id.plan_historia", readonly=True)
    plan_reel = fields.Integer(string="Reels", related="partner_id.plan_reel", readonly=True)
    redes_ids = fields.Many2many("red.social", string="Redes Sociales Activas")
    partner_id = fields.Many2one("res.partner", string="Cliente", required=True, tracking=True)
    industria = fields.Char("Industria del Cliente")
    etapa = fields.Selection([
        ("ideas", "Creación de Ideas"),
        ("reunion", "Reunión con Cliente"),
        ("refinar", "Perfeccionamiento"),
        ("publicaciones", "Publicaciones Listas"),
    ], string="Etapa", default="ideas", group_expand="_expand_etapas")

    # Etapa: Ideas
    notas = fields.Text("Notas")
    usar = fields.Text("Usar")
    evitar = fields.Text("Evitar")
    promtp_ideas = fields.Text("Promtp para Chatpgt")
    ideas_generadas = fields.Html("Ideas Generadas")
    orientacion_comunicacion = fields.Selection([
        ("formativa", "Formativa / Educativa"),
        ("informativa", "Informativa / Profesional"),
        ("emocional", "Emocional / Inspiracional"),
        ("comercial", "Comercial / Persuasiva"),
        ("aspiracional", "Aspiracional / Motivacional"),
        ("relacional", "Relacional / Cercana con la comunidad"),
    ], string="Orientación de la Comunicación", help="Define el enfoque principal del tono con la comunidad o clientes durante esta campaña o mes.")
    tono_comunicacion = fields.Selection([
        ("alegre", "Alegre"),
        ("juvenil", "Juvenil"),
        ("corporativo", "Corporativo"),
        ("empatico", "Empático"),
        ("profesional", "Profesional"),
        ("aspiracional", "Aspiracional"),
    ], string="Tono de Comunicación", help="Define el estilo expresivo o personalidad con la que se comunica la marca en esta campaña.")
    competencia_urls = fields.Text(string="Competencia (URLs)", help="Lista de URLs o referencias de la competencia que pueden servir como inspiración o benchmark.")
    tendencias_urls = fields.Text(string="Tendencias (URLs)", help="Enlaces a videos, imágenes o publicaciones en tendencia relacionadas con la industria.")
    publico_objetivo = fields.Text(string="Público Objetivo", help="Describe el público meta de la campaña: edad, ubicación, intereses, nivel socioeconómico, etc.")
    dias_festivos_referencia = fields.Text(string="Días Festivos / Eventos Relevantes", help="Días festivos o eventos clave sugeridos por IA en función de la industria o temporada.")

    # Etapa: Reunión
    feedback_cliente = fields.Text("Feedback del Cliente")
    anotaciones_cliente = fields.Html("Anotaciones de la Reunión")

    # Etapa: Refinamiento
    plan_base = fields.Html("Plan Base")
    plan_refinado = fields.Html("Plan Refinado")

    # Etapa: Publicaciones
    publicaciones_finales = fields.Html("Publicaciones Finales")
    # Propuestas de contenido
    propuestas_ids = fields.One2many("gl.contenido.propuesta", "flujo_id", string="Propuestas de Contenido")

    # 🔹 Aquí el proyecto de marketing asociado al cliente
    project_id = fields.Many2one("project.project", string="Proyecto Relacionado", domain="[('partner_id', '=', partner_id), ('project_type','=','marketing')]", tracking=True, )

    metricas = fields.Text("Métricas (JSON)")

    def _expand_etapas(self, values, domain):
        return [
            "ideas",
            "reunion",
            "refinar",
            "publicaciones"
        ]

    # Botón 1 → Crear Ideas
    def action_crear_ideas(self):
        for record in self:
            record.etapa = "reunion"

    # Botón 2 → Refinar Propuestas
    def action_refinar_propuestas(self):
        for record in self:
            record.etapa = "refinar"

    # Botón 3 → Generar Tareas
    def action_generar_tareas(self):
        for record in self:
            record.etapa = "publicaciones"

    # Botón volver (ya hecho antes)
    def action_previous_stage(self):
        etapa_order = [
            "ideas",
            "reunion",
            "refinar",
            "publicaciones"
        ]
        for record in self:
            if record.etapa in etapa_order:
                idx = etapa_order.index(record.etapa)
                if idx > 0:
                    record.etapa = etapa_order[idx - 1]

    def action_sugerir_dias_festivos(self):
        """Usa la API de ChatGPT configurada para sugerir de 1 a 3 días festivos o comerciales dentro del rango definido."""
        import requests

        for record in self:
            if not record.industria:
                raise ValidationError("Por favor, define la industria del cliente antes de generar las sugerencias.")

            if not record.date_start or not record.date:
                raise ValidationError("Por favor, define un rango de fechas antes de generar las sugerencias.")

            partner = record.partner_id
            idioma = (partner.lang or "es_ES").split("_")[0]
            pais = partner.country_id.name or "Perú"
            ciudad = partner.city or "Lima"

            # 🧭 Configuración ChatGPT
            icp = self.env["ir.config_parameter"].sudo()
            api_key = icp.get_param("chatgpt.api_key")
            base_url = icp.get_param("chatgpt.base_url", "https://api.openai.com/v1")
            model = icp.get_param("chatgpt.model", "gpt-4.1-mini")

            if not api_key:
                raise ValidationError("No se ha configurado la API Key de ChatGPT en Ajustes del sistema.")

            # 🗓️ Rango de fechas
            rango_texto = f"entre {record.date_start.strftime('%d/%m/%Y')} y {record.date.strftime('%d/%m/%Y')}"

            # 🧠 Prompt simplificado (solo contenido dinámico)
            prompt = (f"Industria: {record.industria}\n"
                      f"Ubicación: {ciudad}, {pais}\n"
                      f"Idioma: {idioma}\n\n"
                      f"Sugiere entre 1 y 3 fechas relevantes para marketing en {pais}, {rango_texto}, "
                      f"incluyendo:\n"
                      f"- Días festivos o conmemorativos culturales y patrios.\n"
                      f"- Días COMERCIALES o de marketing (como Black Friday, CyberDay, Día del Padre, etc.).\n\n"
                      f"Devuelve una lista corta en texto, con cada día en una línea separada, incluyendo el nombre y la fecha aproximada.")

            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Eres un asistente de marketing experto en planificación de contenidos y efemérides. "
                                "Responde de forma breve y estructurada."),
                        },
                        {
                            "role": "user",
                            "content": prompt
                        },
                    ],
                    "temperature": 0.5,
                }

                response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=40)
                response.raise_for_status()
                data = response.json()

                suggestion = data["choices"][0]["message"]["content"].strip()
                record.dias_festivos_referencia = suggestion

            except Exception as e:
                raise ValidationError(f"Error al obtener sugerencias: {e}")

        # 🟩 Notificación + recargar vista
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "🎯 Días Festivos y Comerciales Sugeridos",
                "message": "Se generaron de 1 a 3 sugerencias según el rango de fechas, industria y ubicación del cliente.",
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }

    def action_generate_prompt(self):
        """Genera un prompt completo para IA (orden + JSON base), lo guarda y recarga la vista."""
        import json

        for record in self:
            redes = [r.name for r in record.redes_ids]

            # --- Construcción del JSON base ---
            data = {
                "cliente": {
                    "nombre": record.partner_id.name or "",
                    "industria": record.industria or "",
                    "plan": {
                        "nombre": record.plan_cliente or "",
                        "posts": record.plan_post or 0,
                        "historias": record.plan_historia or 0,
                        "reels": record.plan_reel or 0,
                    },
                    "redes_activas": redes,
                },
                "contexto_creativo": {
                    "etapa": record.etapa,
                    "notas": (record.notas or "").strip(),
                    "usar": (record.usar or "").strip(),
                    "evitar": (record.evitar or "").strip(),
                    "orientacion": record.orientacion_comunicacion or "",
                    "tono": record.tono_comunicacion or "",
                    "publico_objetivo": (record.publico_objetivo or "").strip(),
                    "competencia_urls": (record.competencia_urls or "").strip(),
                    "tendencias_urls": (record.tendencias_urls or "").strip(),
                    "dias_festivos_referencia": (record.dias_festivos_referencia or "").strip(),
                    "rango_fechas": {
                        "inicio": str(record.date_start or ""),
                        "fin": str(record.date or ""),
                    },
                },
                "referencias_metricas": json.loads(record.metricas or "{}"),
                "objetivo_generacion": {
                    "tipo": (
                        "ideas_iniciales" if record.etapa == "ideas" else "refinamiento" if record.etapa == "refinar" else "publicaciones"),
                    "descripcion": ("Generar contenido estratégico alineado al tono, orientación y plan del cliente, "
                                    "considerando métricas previas, público objetivo y calendario de fechas relevantes."),
                },
            }

            # --- JSON compacto ---
            json_base = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

            # --- Construcción de la orden principal ---
            orden = (f"Eres un agente de marketing especializado en \"{record.industria or 'marketing digital'}\". "
                     f"Genera contenido estratégico para redes sociales basado en el siguiente contexto:\n\n"
                     f"- Cliente: {record.partner_id.name or 'Sin nombre especificado'}\n"
                     f"- Periodo: del {record.date_start or '...'} al {record.date or '...'}\n"
                     f"- Público objetivo: {(record.publico_objetivo or 'No especificado').strip()}\n"
                     f"- Publica {record.plan_post or 0} posts y {record.plan_reel or 0} reels.\n"
                     f"- El enfoque de comunicación debe ser {record.orientacion_comunicacion or 'coherente con la marca'} "
                     f"y con un tono {record.tono_comunicacion or 'profesional'}.\n"
                     f"- Utiliza las siguientes redes sociales: {', '.join(redes) if redes else 'sin especificar'}.\n\n"
                     f"Ten en cuenta las siguientes referencias:\n"
                     f"- Competencia: {(record.competencia_urls or 'No se han agregado URLs de referencia').strip()}\n"
                     f"- Tendencias: {(record.tendencias_urls or 'No se han agregado tendencias').strip()}\n"
                     f"- Días festivos relevantes: {(record.dias_festivos_referencia or 'No se han definido eventos').strip()}\n\n"
                     f"Usa el siguiente JSON como base de información:\n\n")

            # --- Guardar el prompt completo ---
            record.promtp_ideas = orden + json_base

        # --- Mostrar notificación y recargar vista ---
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "✅ Prompt IA generado",
                "message": "El JSON y la instrucción se han creado correctamente. Actualizando la vista...",
                "sticky": False,
                "type": "success",
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }
