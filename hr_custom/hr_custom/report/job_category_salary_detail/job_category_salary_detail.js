// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Job Category Salary Detail"] = {
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
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Employee Location",
			description: __("Employee Location. Leave empty for All."),
		},
		{
			fieldname: "payroll_cost_center",
			label: __("Payroll Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Includes child cost centers. Leave empty for All."),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "amount_based_on",
			label: __("Total Salary Based On"),
			fieldtype: "Select",
			options: "Gross Pay\nNet Pay",
			default: "Gross Pay",
			reqd: 1,
		},
	],
};
