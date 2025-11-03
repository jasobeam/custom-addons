import json

import pytz
from odoo import models, fields
from odoo.exceptions import ValidationError
from datetime import datetime


class GeneradorContenidoPropuesta(models.Model):
    _name = "gl.contenido.propuesta"
    _description = "Publicación generada desde IA"
    _rec_name = "titulo"

    flujo_id = fields.Many2one("gl.contenido.flujo", string="Flujo Relacionado", ondelete="cascade")

    titulo = fields.Char("Título", required=True)
    fecha_publicacion = fields.Datetime("Fecha y Hora de Publicación")
    tipo = fields.Selection([
        ("post", "Post"),
        ("reel", "Reel"),
        ("story", "Story"),
    ], string="Tipo de Contenido", default="post")
    descripcion = fields.Text("Descripción")
    texto_en_diseno = fields.Char("Texto en Diseño")
    copy = fields.Text("Copy del Post")
    hashtags = fields.Text("Hashtags")
    recomendaciones = fields.Text("Recomendaciones de Diseño")
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
    promtp_respuesta = fields.Text("Respuesta de Chatpgt")
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
    publicacion_ids = fields.One2many("gl.contenido.propuesta", "flujo_id", string="Ideas / Publicaciones")

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

    def action_ver_calendario(self):
        """Abre las propuestas del flujo actual en vista calendario"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Calendario de Propuestas",
            "res_model": "gl.contenido.propuesta",
            "view_mode": "calendar,form",
            "domain": [
                ("flujo_id", "=", self.id)
            ],
            "context": {
                "default_flujo_id": self.id,
            },
            "target": "current",
        }

    def _expand_etapas(self, values, domain):
        return [
            "ideas",
            "reunion",
            "refinar",
            "publicaciones"
        ]

    # Botón 1 → Crear Ideas
    def action_crear_ideas(self):
        """Valida y convierte el JSON en registros del modelo gl.contenido.propuesta"""
        for record in self:
            # 🕒 Determinar la zona horaria del usuario actual
            user_tz_name = self.env.user.tz or "UTC"
            try:
                tz = pytz.timezone(user_tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC  # fallback si el tz del usuario no es válido

            # 1️⃣ Verificar existencia del JSON
            if not record.promtp_respuesta:
                raise ValidationError("⚠️ El campo 'promtp_respuesta' está vacío. Debes pegar un JSON válido.")

            # 2️⃣ Validar estructura JSON
            try:
                data = json.loads(record.promtp_respuesta)
            except json.JSONDecodeError as e:
                raise ValidationError(f"❌ El contenido no es un JSON válido:\n{e}")

            if not isinstance(data, list):
                raise ValidationError("❌ El JSON debe ser una lista de objetos (ejemplo: [ { ... }, { ... } ])")

            # 3️⃣ Eliminar registros previos (opcional)
            record.publicacion_ids.unlink()

            # 4️⃣ Crear nuevas propuestas
            for item in data:
                if not isinstance(item, dict):
                    raise ValidationError("Cada elemento del JSON debe ser un objeto con claves y valores válidos.")

                # --- Procesar fecha_publicacion ---
                fecha_publicacion_str = item.get("fecha_publicacion")
                fecha_publicacion = False

                if fecha_publicacion_str:
                    if len(fecha_publicacion_str) == 10:
                        fecha_publicacion_str = f"{fecha_publicacion_str} 08:00:00"

                    try:
                        # 1. Convertir string → datetime local
                        fecha_local = datetime.strptime(fecha_publicacion_str, "%Y-%m-%d %H:%M:%S")
                        # 2. Localizar con tz del usuario
                        fecha_local = tz.localize(fecha_local)
                        # 3. Convertir a UTC
                        fecha_utc = fecha_local.astimezone(pytz.UTC)
                        # 4. Remover tzinfo → Odoo espera naive UTC
                        fecha_publicacion = fecha_utc.replace(tzinfo=None)
                    except Exception:
                        raise ValidationError(f"Formato de fecha inválido: {fecha_publicacion_str}. Usa 'YYYY-MM-DD HH:MM:SS'")
                vals = {
                    "flujo_id": record.id,
                    "titulo": item.get("titulo", "Sin título"),
                    "fecha_publicacion": fecha_publicacion,
                    "tipo": item.get("tipo", "post"),
                    "descripcion": item.get("descripcion"),
                    "texto_en_diseno": item.get("texto_en_diseno"),
                    "copy": item.get("copy"),
                    "hashtags": (
                        ", ".join(item.get("hashtags", [])) if isinstance(item.get("hashtags"), list) else item.get("hashtags")),
                    "recomendaciones": item.get("recomendaciones"),
                    "aprobado": False,
                }

                # Validar campos mínimos
                if not vals["titulo"]:
                    raise ValidationError("Cada propuesta debe tener un título válido.")

                self.env["gl.contenido.propuesta"].create(vals)

            # 5️⃣ Avanzar etapa del flujo
            record.etapa = "reunion"

        # 6️⃣ Efecto visual
        return {
            "effect": {
                "fadeout": "slow",
                "message": "✅ Propuestas creadas correctamente desde JSON.",
                "type": "rainbow_man",
            }
        }

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
        """Genera un prompt completo para IA (orden + JSON base + plantilla de salida),
        aplicando DRY: toda la información de contexto vive en el JSON; 'Condiciones' solo define
        formato y cantidades. Maneja fechas/JSON seguros, deduplica URLs y evita llaves conflictivas.
        """
        import json

        def _safe_date_str(d):
            # Devuelve ISO (YYYY-MM-DD) o "" si es None
            try:
                return d.isoformat() if d else ""
            except Exception:
                return ""

        def _safe_date_human(d):
            # Devuelve YYYY-MM-DD legible o "..."
            try:
                return d.isoformat() if d else "..."
            except Exception:
                return "..."

        def _try_json_loads(s):
            try:
                return json.loads(s or "{}")
            except Exception:
                return {}

        def _dedup_lines(s: str) -> str:
            """Recibe texto multilinea, quita líneas vacías, deduplica y conserva orden."""
            if not s:
                return ""
            seen, out = set(), []
            for line in (s.replace("\r", "").split("\n")):
                line = line.strip()
                if not line:
                    continue
                if line not in seen:
                    seen.add(line)
                    out.append(line)
            return "\n".join(out)

        for record in self:
            # --- Datos base seguros ---
            redes = [r.name for r in record.redes_ids] if record.redes_ids else []
            partner = record.partner_id
            idioma = (partner.lang or "es_ES").split("_")[0]
            pais = partner.country_id.name or "Perú"
            ciudad = partner.city or "Lima"

            fecha_ini_iso = _safe_date_str(record.date_start)
            fecha_fin_iso = _safe_date_str(record.date)
            fecha_ini_human = _safe_date_human(record.date_start)
            fecha_fin_human = _safe_date_human(record.date)

            # Deduplicar URLs
            competencia_clean = _dedup_lines((record.competencia_urls or "").strip())
            tendencias_clean = _dedup_lines((record.tendencias_urls or "").strip())
            dias_clean = (record.dias_festivos_referencia or "").strip()

            metricas = _try_json_loads(record.metricas)

            # --- JSON base (ÚNICA FUENTE de reglas de contexto) ---
            data = {
                "cliente": {
                    "nombre": partner.name or "",
                    "industria": record.industria or "",

                    "redes_activas": redes,
                },
                "contexto_creativo": {
                    "etapa": record.etapa,
                    "notas": (record.notas or "").strip(),
                    "usar": (record.usar or "").strip(),
                    "evitar": (record.evitar or "").strip(),  # Reglas: quedan solo aquí (no se repiten en Condiciones)
                    "orientacion": record.orientacion_comunicacion or "",
                    "tono": record.tono_comunicacion or "",
                    "publico_objetivo": (record.publico_objetivo or "").strip(),
                    "competencia_urls": competencia_clean,
                    "tendencias_urls": tendencias_clean,
                    "dias_festivos_referencia": dias_clean,
                    "rango_fechas": {
                        "inicio": fecha_ini_iso,
                        "fin": fecha_fin_iso
                    },
                    "idioma": idioma,
                    "ubicacion": {
                        "ciudad": ciudad,
                        "pais": pais
                    },
                },
                "referencias_metricas": metricas,
                "objetivo_generacion": {
                    "tipo": (
                        "ideas_iniciales" if record.etapa == "ideas" else "refinamiento" if record.etapa == "refinar" else "publicaciones"),
                    "descripcion": (
                        "Generar contenido alineado al contexto creativo (tono, orientación, idioma, público, fechas), "
                        f"apoyado en métricas previas y con foco en la industria del cliente "
                        f"({record.industria or 'especificada por el cliente'})."),
                },
            }

            # --- JSON base compacto ---
            json_base = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

            # --- Prompt contextual (DRY: no repetir lo que ya está en el JSON) ---
            orden = ("Eres un agente de marketing especializado en el sector indicado. "
                     "Lee el siguiente JSON y, sin reescribirlo ni resumirlo, úsalo como única fuente de verdad.\n\n"
                     f"{json_base}\n\n")

            # --- Plantilla de salida: SOLO formato + cantidades; remite a `contexto_creativo` ---
            # OJO: llaves escapadas {{ }} por uso de .format()
            instruccion_json = (
                "A partir del contexto anterior, genera un JSON estructurado con el plan de publicaciones del periodo. "
                "Devuelve ÚNICAMENTE el JSON con la siguiente estructura:\n\n"
                "[\n"
                "  {{\n"
                "    \"titulo\": \"string\",\n"
                "    \"fecha_publicacion\": \"YYYY-MM-DD HH:MM:SS\",\n"
                "    \"tipo\": \"post | reel | historia | carrusel\",\n"
                "    \"descripcion\": \"Breve resumen del contenido y su objetivo comunicacional.\",\n"
                "    \"texto_en_diseno\": \"Frase principal que aparecerá en la pieza gráfica o portada del video.\",\n"
                "    \"copy\": \"Texto para la publicación (copy AIDA).\",\n"
                "    \"hashtags\": [\"#hashtag1\", \"#hashtag2\", \"#hashtag3\"],\n"
                "    \"recomendaciones\": \"Sugerencias sobre estilo visual, elementos gráficos, colores, encuadre o tono.\"\n"
                "  }}\n"
                "]\n\n"
                "Condiciones:\n"
                "- Genera {posts} posts y {reels} reels según el plan.\n"
                "- Respeta estrictamente TODO lo definido en `contexto_creativo` (tono, orientación, idioma, público_objetivo, "
                "fechas, usar/evitar, ubicación).\n"
                "- Entrega solo el JSON sin explicaciones adicionales.").format(posts=int(record.plan_post or 0), reels=int(record.plan_reel or 0))

            # --- Guardar el prompt completo ---
            record.promtp_ideas = orden + instruccion_json

        # --- Notificación visual ---
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "✅ Prompt IA generado",
                "message": "Prompt generado sin redundancias (DRY). Actualizando la vista...",
                "sticky": False,
                "type": "success",
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload"
                },
            },
        }
