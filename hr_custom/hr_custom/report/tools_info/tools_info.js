// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Tools Info"] = {
	filters: [
		{ fieldname: "location", label: __("Location"), fieldtype: "Link", options: "Location" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "item_code", label: __("Item Code"), fieldtype: "Link", options: "Item" },
		{ fieldname: "asset_no", label: __("Asset"), fieldtype: "Link", options: "Asset" },
		{
			fieldname: "tool_status",
			label: __("Tool Status"),
			fieldtype: "Select",
			options: ["", "Active", "Not Be Available For Transfer"],
		},
		{ fieldname: "from_date", label: __("Stk Issue From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Stk Issue To"), fieldtype: "Date" },
	],
};
