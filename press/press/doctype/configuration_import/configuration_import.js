// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on("Configuration Import", {
    setup(frm) {
        frm.trigger("update_primary_action");

        frm.has_import_file = () => {
            return (frm.doc.sheet_type == "Google Sheets" && frm.doc.google_sheet_access_status == "Accessible") || (frm.doc.sheet_type == "Excel" && frm.doc.excel_file);
        };
    },

    onload_post_render(frm) {
        frm.trigger("update_primary_action");
    },

    refresh(frm) {
        frm.trigger("show_import_log");
    },

    show_failed_logs(frm) {
        frm.trigger('show_import_log');
    },

    show_import_log(frm) { 
        const import_log = JSON.parse(frm.doc.import_log || "[]");

        let rows = import_log
            .map((log) => {
                let html = "";
                let indicator_color = "red";
                let title = __("Error");

                if (log.status === "Success") {
                    indicator_color = "green";
                    title = __("Success");
                }

                if (frm.doc.show_failed_logs && log.status === "Success") {
					return '';
				}

                return `<tr>
                    <td>${log.row}</td>
                    <td>
                        <div class="indicator ${indicator_color}">${title}</div>
                    </td>
                    <td>
                        ${log.message}
                    </td>
                </tr>`;
            })
            .join("");

        if (!rows) {
            rows = `<tr><td class="text-center text-muted" colspan=3>
                ${__("No logs to show")}
            </td></tr>`;
        }

        frm.get_field("import_log_preview").$wrapper.html(`
            <table class="table table-bordered">
                <tr class="text-muted">
                    <th width="20%">${__("Row")}</th>
                    <th width="20%">${__("Status")}</th>
                    <th width="60%">${__("Message")}</th>
                </tr>
                ${rows}
            </table>
        `);
    },

    test_permissions(frm) {
        frm.call({
            method: "test_google_sheet_permission",
            freeze: true,
            freeze_message: "Testing Google Sheet access...",
            doc: frm.doc,
            callback: function(r) {
                if (r.message) {
                    frm.set_value("google_sheet_access_status", r.message);
                }
            }
        });
    },

    google_sheet_url(frm) {
        frm.set_value("google_sheet_access_status", "Not Tested");
    },

    google_sheet_access_status(frm) {
        frm.trigger("update_primary_action");
    },

    excel_file(frm) {
        frm.trigger("update_primary_action");
    },

    update_primary_action(frm) {
        if (frm.is_dirty()) {
            frm.enable_save();
            return;
        }
        frm.disable_save();
        if (frm.doc.status !== "Success") {
            if (!frm.is_new() && frm.has_import_file()) {
                let label = frm.doc.status === "Pending" ? __("Start Import") : __("Retry");
                frm.page.set_primary_action(label, () => frm.events.start_import(frm));
            } else {
                frm.page.set_primary_action(__("Save"), () => frm.save());
            }
        }
    },

    start_import(frm) {
        frm.call({
            method: "start_import",
            doc: frm.doc,
            callback: function(r) {
                frm.disable_save();
                frm.refresh();
            }
        });
    }
});
