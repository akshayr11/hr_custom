// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Salary Summary Cost Center Wise"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: moment.months(),
			default: moment().format("MMMM"),
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "payroll_cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Includes child cost centers. Leave empty for All."),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
	],

	// month heading and total rows in bold; nothing shown in the empty cells of a heading row
	formatter(value, row, column, data, default_formatter) {
		if (data && data.is_heading && column.fieldname !== "location") return "";
		value = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
