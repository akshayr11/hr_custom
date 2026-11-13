// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Attendance Details"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
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
			fieldname: "code",
			label: __("Code"),
			fieldtype: "Select",
			options: ["", "P", "L", "E", "LV", "R", "A", "Ex"],
			description: __("P Present, L Late, E Early Exit, LV Leave, R Rest Day, A Absent, Ex Exception"),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const color = { P: "green", L: "orange", E: "orange", LV: "blue", R: "gray", A: "red", Ex: "purple" }[data.code];
		if (column.fieldname === "code" && color) {
			value = `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>`;
		}
		if (["late_in", "early_out", "deduction_minutes"].includes(column.fieldname) && data[column.fieldname] > 0) {
			value = `<span style="color: var(--red-600);">${value}</span>`;
		}
		return data.bold ? `<b>${value}</b>` : value;
	},
};
