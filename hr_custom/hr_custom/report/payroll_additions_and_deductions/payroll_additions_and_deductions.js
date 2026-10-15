// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Payroll Additions and Deductions"] = {
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
			options: [
				"January",
				"February",
				"March",
				"April",
				"May",
				"June",
				"July",
				"August",
				"September",
				"October",
				"November",
				"December",
			],
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
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Employee Location",
			description: __("Employee Location. Leave empty for All."),
		},
		{
			fieldname: "payroll_cost_center",
			label: __("Costing Location"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Payroll Cost Center (includes child cost centers). Leave empty for All."),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.addition) value = `<span style="color: var(--green-600)">${value}</span>`;
		if (column.deduction) value = `<span style="color: var(--red-600)">${value}</span>`;
		return value;
	},
};
