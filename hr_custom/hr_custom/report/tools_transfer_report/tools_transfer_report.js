// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Tools Transfer Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "tool_no", label: __("Tool No"), fieldtype: "Link", options: "Tool Registry" },
		{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Location",
			description: __("Source or Target"),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			description: __("From or To"),
		},
	],
};
