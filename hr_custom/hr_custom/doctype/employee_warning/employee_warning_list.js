// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Warning"] = {
	add_fields: ["status", "action"],
	has_indicator_for_draft: true,
	get_indicator(doc) {
		const colors = { Open: "orange", Approved: "green", Rejected: "red", Cancelled: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
