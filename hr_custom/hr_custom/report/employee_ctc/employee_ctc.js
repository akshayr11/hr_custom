// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["Employee CTC"] = {
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
			default: moment().subtract(1, "month").format("MMMM"),
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: moment().subtract(1, "month").year(),
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
			description: __("Payroll Cost Center (includes child cost centers)"),
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "designation",
			label: __("Job Title"),
			fieldtype: "Link",
			options: "Designation",
		},
		{
			fieldname: "employee_category",
			label: __("Employee Category"),
			fieldtype: "Select",
			options: ["All", "Omani", "Expat"],
			default: "All",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],

	onload(report) {
		report.page.add_inner_button(__("CTC Settings"), () => frappe.set_route("Form", "Employee CTC Settings"));
	},
};
