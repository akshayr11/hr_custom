// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.listview_settings["OHB Bank Loan"] = {
	add_fields: ["status", "docstatus", "balance_amount"],
	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "red", "docstatus,=,2"];
		if (doc.docstatus === 0) return [__("Draft"), "gray", "docstatus,=,0"];
		if (doc.balance_amount <= 0) return [__("Fully Paid"), "blue", "balance_amount,<=,0|docstatus,=,1"];
		return doc.status === "Active"
			? [__("Active"), "green", "status,=,Active|docstatus,=,1"]
			: [__("Inactive"), "orange", "status,=,Inactive|docstatus,=,1"];
	},
};
