// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Checkin Upload", {
	refresh(frm) {
		frm.add_custom_button(__("Download Template"), () => {
			window.open(
				"/api/method/hr_custom.hr_custom.doctype.employee_checkin_upload.employee_checkin_upload.download_template"
			);
		});

		if (!frm.is_new() && frm.doc.checkin_file && ["Draft", "Partly Uploaded", "Failed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Upload Check-ins"), () => {
				frm.call({ doc: frm.doc, method: "upload", freeze: true, freeze_message: __("Uploading check-ins...") }).then(
					() => frm.reload_doc()
				);
			}).addClass("btn-primary");
		}

		if (frm.doc.created_checkins) {
			frm.add_custom_button(__("Check-ins"), () =>
				frappe.set_route("List", "Employee Checkin", { device_id: frm.doc.name })
			);
		}
	},
});
