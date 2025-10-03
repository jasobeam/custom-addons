/** @odoo-module **/

import { registry } from "@web/core/registry";

registry.category("actions").add("clipboard_copy", async (env, action) => {
    try {
        await navigator.clipboard.writeText(action.params.content);
        env.services.notification.add("✅ JSON copiado al portapapeles", { type: "success" });
    } catch (e) {
        env.services.notification.add("❌ No se pudo copiar: " + e, { type: "danger" });
    }
});