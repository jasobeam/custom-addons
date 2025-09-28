/** @odoo-module **/

    const calendarEl = document.getElementById("task_calendar");
    if (!calendarEl) {
        return;
    }

    if (typeof FullCalendar === "undefined") {
        return;
    }

    const projectId = calendarEl.getAttribute("data-project-id");

    // Crear calendario CONECTADO al controlador
    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: "dayGridMonth",
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth'
        },
        locale: 'es',
        buttonText: {
            today: 'Hoy',
            month: 'Mes',
            week: 'Semana',
            day: 'Día'
        },
        events: function(fetchInfo, successCallback, failureCallback) {


            // Llamar al endpoint del controlador
            fetch(`/my/projects/${projectId}/calendar/events`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    start: fetchInfo.start.toISOString(),
                    end: fetchInfo.end.toISOString()
                })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Error HTTP: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                const events = data.result || [];   // 👈 Extraemos solo el array
                successCallback(events);
            })
            .catch(err => {
                failureCallback(err);
            });
        },
        eventClick: function(info) {
            // Navegar a la tarea cuando se hace click
            if (info.event.url) {
                window.location.href = info.event.url;
            } else {
                window.location.href = `/my/projects/${projectId}/task/${info.event.id}`;
            }
        },
        eventDidMount: function(info) {
            // Tooltip con información
            const taskId = info.event.id;
            const title = info.event.title;
            const startDate = info.event.start ? info.event.start.toLocaleDateString('es-ES') : 'Sin fecha';

            info.el.setAttribute('title', `${title}\nFecha: ${startDate}\nID: ${taskId}`);
            info.el.style.cursor = 'pointer';
        },

        loading: function(isLoading) {
            const statusEl = document.getElementById('calendar_status');
            if (statusEl) {
                if (isLoading) {
                    statusEl.innerHTML = '🔄 Cargando eventos...';
                    statusEl.className = 'alert alert-warning';
                } else {
                    statusEl.innerHTML = '✅ Calendario cargado';
                    statusEl.className = 'alert alert-success';
                }
            }
        }
    });

    calendar.render();

