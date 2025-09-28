from odoo import http
from odoo.http import request
from datetime import datetime


class PortalProjectCalendar(http.Controller):

    @http.route('/my/projects/<int:project_id>/calendar', type='http', auth="user", website=True)
    def portal_project_calendar(self, project_id, **kw):
        project = request.env['project.project'].search([
            ('id', '=', project_id),
            '|',
            ('privacy_visibility', '=', 'portal'),
            ('message_partner_ids', 'in', [
                request.env.user.partner_id.id
            ])
        ])

        if not project:
            return request.redirect('/my')

        return request.render('gl_geniolibre.portal_project_calendar_page', {
            'project': project,
        })

    @http.route('/my/projects/<int:project_id>/calendar/events', type='json', auth="user", methods=[
        'POST'
    ], website=True)
    def portal_project_calendar_events(self, project_id, start=None, end=None, **kw):
        print(f"📡 Solicitando eventos para proyecto {project_id}")

        # Verificar proyecto
        project = request.env['project.project'].search([
                                                            ('id', '=', project_id)
                                                        ])
        if not project.exists():
            return {
                "error": "Proyecto no encontrado"
            }

        # Construir dominio de búsqueda
        domain = [
            ('project_id', '=', project_id)
        ]

        # Filtrar por fechas si se proporcionan
        if start:
            try:
                start_date = datetime.fromisoformat(start.replace('Z', '+00:00'))
                domain.append(('fecha_publicacion', '>=', start_date.date()))
            except Exception as e:
                print(f"⚠️ Error parseando start date: {e}")

        if end:
            try:
                end_date = datetime.fromisoformat(end.replace('Z', '+00:00'))
                domain.append(('fecha_publicacion', '<=', end_date.date()))
            except Exception as e:
                print(f"⚠️ Error parseando end date: {e}")

        # Buscar tareas
        tasks = request.env['project.task'].search(domain)
        print(f"📋 Encontradas {len(tasks)} tareas")

        events = []
        for task in tasks:
            if task.fecha_publicacion:
                event_data = {
                    "id": task.id,
                    "title": task.name,
                    "start": task.fecha_publicacion.isoformat(),  # ISO para FullCalendar
                    "allDay": False,  # mostrar fecha y hora
                    "url": f"/my/projects/{project_id}/task/{task.id}",
                    "color": self._get_status_color(task.post_estado),
                    "extendedProps": {
                        "estado": task.post_estado or "sin estado",
                        "fecha_publicacion": task.fecha_publicacion.strftime("%d/%m/%Y %H:%M"),
                        # 👈 formato dd/MM/yyyy HH:mm
                    }
                }
                events.append(event_data)

        print(f"✅ Enviando {len(events)} eventos")
        print(events)
        return events

    def _get_status_color(self, status):
        """Asignar colores según el estado de la tarea"""
        color_map = {
            'borrador': '#6c757d',  # Gris
            'programado': '#ffc107',  # Amarillo
            'publicado': '#28a745',  # Verde
            'completado': '#fd7e14',  # Anaranjado (Bootstrap orange)
            'cancelado': '#dc3545',  # Rojo
        }
        return color_map.get(status, '#007bff')  # Azul por defecto