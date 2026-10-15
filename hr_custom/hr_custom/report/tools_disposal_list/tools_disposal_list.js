// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Tools Disposal List"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "location", label: __("Location"), fieldtype: "Link", options: "Location" },
		{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Link", options: "Item" },
		{ fieldname: "tool_no", label: __("Tool No"), fieldtype: "Link", options: "Tool Registry" },
	],
};
