// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Freeze Basic", {
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
	},
});
