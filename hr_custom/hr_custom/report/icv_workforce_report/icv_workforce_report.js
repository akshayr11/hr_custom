// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["ICV Workforce Report"] = {
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
			fieldname: "from_month",
			label: __("From Month"),
			fieldtype: "Select",
			options: moment.months(),
			default: moment().subtract(1, "month").format("MMMM"),
			reqd: 1,
		},
		{
			fieldname: "from_year",
			label: __("From Year"),
			fieldtype: "Int",
			default: moment().subtract(1, "month").year(),
			reqd: 1,
		},
		{
			fieldname: "to_month",
			label: __("To Month"),
			fieldtype: "Select",
			options: moment.months(),
			default: moment().format("MMMM"),
			reqd: 1,
		},
		{
			fieldname: "to_year",
			label: __("To Year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "payroll_cost_center",
			label: __("Location (Cost Center)"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Includes child cost centers. Leave empty for All."),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "employee_category",
			label: __("Emp Category"),
			fieldtype: "Select",
			options: ["All", "Omani", "Expat"],
			default: "All",
		},
		{
			fieldname: "usd_rate",
			label: __("USD Exchange Rate"),
			fieldtype: "Float",
			precision: 6,
			description: __("USD for 1 unit of the company currency. Leave empty to use Currency Exchange."),
		},
	],
};
