// approved annual leave: record the employee's actual rejoining
frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.status !== "Approved") return;
		frappe.db.get_value("Leave Type", frm.doc.leave_type, "rejoining_required").then((r) => {
			if (!(r.message && r.message.rejoining_required)) return;
			frm.add_custom_button(
				__("Rejoining"),
				() =>
					frappe.new_doc("Employee Rejoining", {
						employee: frm.doc.employee,
						leave_application: frm.doc.name,
					}),
				__("Create")
			);
		});
	},
});
