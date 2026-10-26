// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Gratuity Details"] = {
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
			fieldname: "as_on_date",
			label: __("As on Date"),
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
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "employee_category",
			label: __("Employee Category"),
			fieldtype: "Select",
			options: ["All", "Expat", "Omani"],
			default: "Expat",
		},
		{
			fieldname: "eligible_only",
			label: __("Eligible Only"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "grand_total" && data && !data.is_total_row) {
			value = `<b>${value}</b>`;
		}
		if (column.fieldname === "remarks" && data?.remarks) {
			value = `<span class="text-muted">${value}</span>`;
		}
		return value;
	},
};
