// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

const ATTENDANCE_CODE_COLORS = {
	P: "green",
	L: "orange",
	E: "orange",
	LV: "blue",
	R: "gray",
	A: "red",
	Ex: "purple",
};

frappe.query_reports["Attendance Detailed Report"] = {
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
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const color = /^d\d+$/.test(column.fieldname) && ATTENDANCE_CODE_COLORS[data && data[column.fieldname]];
		return color ? `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>` : value;
	},
};
