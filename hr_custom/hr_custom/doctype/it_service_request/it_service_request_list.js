// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.listview_settings["IT Service Request"] = {
	add_fields: ["status"],
	has_indicator_for_draft: true,
	get_indicator(doc) {
		const colors = {
			Draft: "red",
			"Pending for Submission": "orange",
			Submitted: "yellow",
			Reopened: "pink",
			Received: "blue",
			"In Progress": "purple",
			Completed: "green",
			Closed: "gray",
			Cancelled: "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
