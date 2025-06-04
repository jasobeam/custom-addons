/** @odoo-module **/

import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

export class ChatroomView extends Component {
    static template = "whatsapp.chatroom.owl";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            chatrooms: [],
            selected: null,
            messages: [],
            attachedFile: null,
            fileName: "",
            filePreview: null,
            partnerData: null,
            fileType: null,
            activeTab: 'reply',
            suggestedMessages: [],
            selectedMessage: null
        });

        // Referencias
        this.inputRef = useRef("inputMessage");
        this.customMessageInput = useRef("customMessageInput");
        this.fileInputRef = useRef("file-input");

        // Binding de métodos
        this.toggleEmojiPicker = this.toggleEmojiPicker.bind(this);
        this.insertEmoji = this.insertEmoji.bind(this);

        onWillStart(async () => {
            console.log("[DEBUG] Iniciando carga inicial de datos...");

            try {
                console.log("[DEBUG] Buscando chatrooms...");
                const rooms = await this.orm.call('whatsapp.chatroom', 'search_read', [[['state', '=', 'open']]]);
                console.log("[DEBUG] Chatrooms encontrados:", rooms);

                this.state.chatrooms = rooms;

                if (rooms.length > 0) {
                    console.log("[DEBUG] Cargando primer chatroom...");
                    this.state.selected = rooms[0];
                    this.state.messages = await this._loadMessages(rooms[0]);

                    // Cargar datos del partner si existe
                    if (rooms[0].partner_id) {
                        console.log("[DEBUG] Partner_id encontrado:", rooms[0].partner_id);
                        console.log("[DEBUG] Intentando cargar datos del partner con ID:", rooms[0].partner_id[0]);

                        try {
                            const partnerData = await this.orm.read(
                                'res.partner',
                                [rooms[0].partner_id[0]],
                                ['name', 'email', 'phone', 'image_1920']
                            );
                            console.log("[DEBUG] Datos del partner obtenidos:", partnerData);

                            this.state.partnerData = partnerData[0];
                        } catch (error) {
                            console.error("[ERROR] Falló al cargar partner:", error);
                        }
                    } else {
                        console.log("[DEBUG] No hay partner_id en este chatroom");
                    }
                } else {
                    console.log("[DEBUG] No se encontraron chatrooms");
                }

                // Cargar mensajes automáticos
                console.log("[DEBUG] Cargando mensajes automáticos...");
                this.state.suggestedMessages = await this.orm.searchRead(
                    'mensajes.automaticos',
                    [['activo', '=', true]],
                    ['name', 'contenido'],
                    { order: 'prioridad asc' }
                );
                console.log("[DEBUG] Mensajes automáticos cargados:", this.state.suggestedMessages.length);

            } catch (error) {
                console.error("[ERROR] Error en carga inicial:", error);
            }
        });
    }
//////////////////////////////////////////// Mostrar respuestas sugeridas
    handleSelectMessage(ev) {
        const messageId = parseInt(ev.target.value);
        this.state.selectedMessage = this.state.suggestedMessages.find(msg => msg.id === messageId) || null;
    }
    sendSuggestedMessage() {
        if (this.state.selectedMessage) {
            alert(this.state.selectedMessage.contenido); // Cambiar esto por tu lógica de envío real
            // this.env.services.notification.add("Mensaje enviado: " + this.state.selectedMessage.name);
        } else {
            alert("Por favor selecciona un mensaje");
        }
    }
    sendCustomMessage() {
        const message = this.customMessageInput.el.value.trim();

        if (message) {
            alert(`Mensaje a enviar: ${message}`);
            // this.env.services.notification.add(`Mensaje enviado: ${message}`);

            // Opcional: Limpiar el textarea después de enviar
            this.customMessageInput.el.value = "";
        } else {
            alert("Por favor escribe un mensaje");
        }
    }
//////////////////////////////////////////// Adjuntar archivos

    openFilePicker() {this.fileInputRef.el.click();}
    handleFileChange(ev) {
        const file = ev.target.files[0];
        if (!file) return;

        // Validar tipo de archivo
        const isImage = file.type.match('image.*');
        const isPDF = file.type === 'application/pdf';
        const isExcel = file.type.match('application/vnd.ms-excel') ||
                       file.type.match('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');

        if (!isImage && !isPDF && !isExcel) {
            this.displayFileError("Solo se permiten imágenes (JPG, PNG), PDFs y archivos Excel");
            return;
        }

        this.state.attachedFile = file;
        this.state.fileName = file.name;
        this.state.fileType = isImage ? 'image' : (isPDF ? 'pdf' : 'excel');

        // Crear vista previa
        if (isImage) {
            const reader = new FileReader();
            reader.onload = (e) => {
                this.state.filePreview = e.target.result;
            };
            reader.readAsDataURL(file);
        } else {
            // Vista previa para PDF o Excel
            this.state.filePreview = this.getFileIcon(this.state.fileType);
        }
    }
    getFileIcon(fileType) {
        const icons = {
            pdf: '/web/static/src/img/pdf_icon.png',
            excel: '/web/static/src/img/excel_icon.png'
        };
        return icons[fileType] || '/web/static/src/img/file_icon.png';
    }
    displayFileError(message) {
        // Implementa tu lógica para mostrar errores
        console.error(message);
        // Puedes usar un servicio de notificación de Odoo aquí
        this.fileInputRef.el.value = ""; // Limpiar input
    }
    removeAttachment() {
        this.state.attachedFile = null;
        this.state.fileName = "";
        this.state.filePreview = null;
        this.fileInputRef.el.value = ""; // Resetear input file
    }
//////////////////////////////////////////// Insertar Emojis
    insertEmoji(emoji) {
        const input = this.inputRef.el;
        if (!input) return;
        const start = input.selectionStart || 0;
        const end = input.selectionEnd || 0;
        input.value = input.value.slice(0, start) + emoji + input.value.slice(end);
        input.selectionStart = input.selectionEnd = start + emoji.length;
//        input.focus();
//        this.state.showEmojiPicker = false;
    }
    toggleEmojiPicker() {
        this.state.showEmojiPicker = !this.state.showEmojiPicker;
        if (this.state.showEmojiPicker) {
            // Agregar el event listener solo cuando se abre el picker
            document.addEventListener('click', this.closeEmojiPickerOnClickOutside);
        } else {
            this.removeClickListener();
        }
    }
//////////////////////////////////////////// Cerrar Tooltip Emojis
    closeEmojiPickerOnClickOutside = (event) => {
        const emojiPicker = document.getElementById('emoji-picker');
        if (emojiPicker && !emojiPicker.contains(event.target)) {
            // Si el click fue fuera del emoji picker, cerrarlo
            this.state.showEmojiPicker = false;
            this.removeClickListener();
        }
    }
    removeClickListener() {document.removeEventListener('click', this.closeEmojiPickerOnClickOutside);}

    // Limpiar el event listener cuando el componente se destruya
    __destroy() {
        this.removeClickListener();
        super.__destroy();
    }
//////////////////////////////////////////// Cargo de datos asyncronos
    async selectChatroom(chat) {
        console.log("[DEBUG] Seleccionando chatroom:", chat.id);

        // 1. Primero actualiza el chat seleccionado
        this.state.selected = chat;

        // 2. Mantén los datos del partner anterior mientras se cargan los nuevos
        const previousPartnerData = this.state.partnerData;

        // 3. Carga los mensajes
        this.state.messages = await this._loadMessages(chat);

        // 4. Verifica si hay partner_id antes de hacer reset
        if (!chat.partner_id) {
            console.log("[DEBUG] No hay partner_id, estableciendo partnerData a null");
            this.state.partnerData = null;
        } else {
            console.log("[DEBUG] Cargando partner para chat:", chat.id);
            try {
                const partnerData = await this.orm.read(
                    'res.partner',
                    [chat.partner_id[0]],
                    ['name', 'email', 'phone', 'image_1920']
                );
                console.log("[DEBUG] Partner data obtenida:", partnerData);
                this.state.partnerData = partnerData[0];
            } catch (error) {
                console.error("[ERROR] Error al cargar partner:", error);
                this.state.partnerData = null;
            }
        }
    }


    async _loadMessages(chat) {
        console.log("[DEBUG] Cargando mensajes para chat:", chat.id);
        const messages = await this.orm.call(
            'whatsapp.chatmessage',
            'search_read',
            [[['chatroom_id', '=', chat.id]]]
        );
        console.log("[DEBUG] Mensajes cargados:", messages.length);
        return messages;
    }
}

registry.category("actions").add("whatsapp.chatroom.owl", ChatroomView);