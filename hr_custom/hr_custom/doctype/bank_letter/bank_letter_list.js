// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.listview_settings["Bank Letter"] = {
	add_fields: ["ot_type", "docstatus"],
	has_indicator_for_draft: true,
	get_indicator(doc) {
		const colors = { "With OT": "green", "Without OT": "orange", "OT Only": "blue" };
		const prefix = doc.docstatus === 0 ? __("Draft") + ": " : "";
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		return [prefix + __(doc.ot_type), colors[doc.ot_type] || "gray", `ot_type,=,${doc.ot_type}`];
	},
};
