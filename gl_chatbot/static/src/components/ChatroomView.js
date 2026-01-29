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
            fileType: null,
            partnerData: null,
            partnerOrders: [],
            activeTab: 'reply',
            suggestedMessages: [],
            selectedMessage: null
        });
        this.STATE_LABELS = {
            draft: "Borrador",
            sent: "Enviado",
            sale: "Confirmado",
            done: "Hecho",
            cancel: "Cancelado",
        };

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
                const rooms = await this.orm.call('whatsapp.chatroom', 'search_read', [[['state', '=', 'open']]]);
                this.state.chatrooms = rooms;

                if (rooms.length > 0) {
                    this.state.selected = rooms[0];
                    this.state.messages = await this._loadMessages(rooms[0]);

                    if (rooms[0].partner_id) {
                        await this._loadPartnerInfo(rooms[0].partner_id[0]);
                    }
                }

                this.state.suggestedMessages = await this.orm.searchRead(
                    'mensajes.automaticos',
                    [['activo', '=', true]],
                    ['name', 'contenido'],
                    { order: 'prioridad asc' }
                );

            } catch (error) {
                console.error("[ERROR] Error en carga inicial:", error);
            }
        });
    }

    // Cargar datos del partner y sus documentos de venta
    async _loadPartnerInfo(partnerId) {
        try {
            const partnerData = await this.orm.read(
                'res.partner',
                [partnerId],
                ['name', 'email', 'phone', 'image_1920', 'mobile', 'street', 'city']
            );
            this.state.partnerData = partnerData[0];

            const orders = await this.orm.searchRead(
                'sale.order',
                [['partner_id', '=', partnerId]],
                ['id', 'name', 'state', 'date_order', 'currency_id', 'amount_total'],
                { order: 'date_order desc', limit: 10 }
            );
            this.state.partnerOrders = orders;
        } catch (error) {
            console.error("[ERROR] Error al obtener info del partner:", error);
            this.state.partnerData = null;
            this.state.partnerOrders = [];
        }
    }

    // Manejo de selección de chatroom
    async selectChatroom(chat) {
        this.state.selected = chat;
        this.state.messages = await this._loadMessages(chat);

        if (chat.partner_id) {
            await this._loadPartnerInfo(chat.partner_id[0]);
        } else {
            this.state.partnerData = null;
            this.state.partnerOrders = [];
        }
    }

    async _loadMessages(chat) {
        const messages = await this.orm.call(
            'whatsapp.chatmessage',
            'search_read',
            [[['chatroom_id', '=', chat.id]]]
        );
        return messages;
    }

    // Respuestas sugeridas
    handleSelectMessage(ev) {
        const messageId = parseInt(ev.target.value);
        this.state.selectedMessage = this.state.suggestedMessages.find(msg => msg.id === messageId) || null;
    }

    sendSuggestedMessage() {
        if (this.state.selectedMessage) {
            alert(this.state.selectedMessage.contenido);
        } else {
            alert("Por favor selecciona un mensaje");
        }
    }

    sendCustomMessage() {
        const message = this.customMessageInput.el.value.trim();
        if (message) {
            alert(`Mensaje a enviar: ${message}`);
            this.customMessageInput.el.value = "";
        } else {
            alert("Por favor escribe un mensaje");
        }
    }

    // Adjuntar archivos
    openFilePicker() {
        this.fileInputRef.el.click();
    }

    handleFileChange(ev) {
        const file = ev.target.files[0];
        if (!file) return;

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

        if (isImage) {
            const reader = new FileReader();
            reader.onload = (e) => {
                this.state.filePreview = e.target.result;
            };
            reader.readAsDataURL(file);
        } else {
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
        console.error(message);
        this.fileInputRef.el.value = "";
    }

    removeAttachment() {
        this.state.attachedFile = null;
        this.state.fileName = "";
        this.state.filePreview = null;
        this.fileInputRef.el.value = "";
    }

    // Emojis
    insertEmoji(emoji) {
        const input = this.inputRef.el;
        if (!input) return;
        const start = input.selectionStart || 0;
        const end = input.selectionEnd || 0;
        input.value = input.value.slice(0, start) + emoji + input.value.slice(end);
        input.selectionStart = input.selectionEnd = start + emoji.length;
    }

    toggleEmojiPicker() {
        this.state.showEmojiPicker = !this.state.showEmojiPicker;
        if (this.state.showEmojiPicker) {
            document.addEventListener('click', this.closeEmojiPickerOnClickOutside);
        } else {
            this.removeClickListener();
        }
    }

    closeEmojiPickerOnClickOutside = (event) => {
        const emojiPicker = document.getElementById('emoji-picker');
        if (emojiPicker && !emojiPicker.contains(event.target)) {
            this.state.showEmojiPicker = false;
            this.removeClickListener();
        }
    }

    removeClickListener() {
        document.removeEventListener('click', this.closeEmojiPickerOnClickOutside);
    }

    __destroy() {
        this.removeClickListener();
        super.__destroy();
    }
}

registry.category("actions").add("whatsapp.chatroom.owl", ChatroomView);
