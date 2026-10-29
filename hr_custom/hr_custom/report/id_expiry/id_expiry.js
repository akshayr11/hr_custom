// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.query_reports["ID Expiry"] = {
	filters: [
		{
			fieldname: "id_type",
			label: __("ID Type"),
			fieldtype: "Select",
			options: ["Passport", "Visa", "Civil ID", "Driving License", "All"],
			default: "Passport",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), 3),
			reqd: 1,
		},
		{
			fieldname: "employee_category",
			label: __("Omani/Expat"),
			fieldtype: "Select",
			options: ["All", "Expat", "Omani"],
			default: "All",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "status",
			label: __("Employee Status"),
			fieldtype: "Select",
			options: ["", "Active", "Inactive", "Suspended", "Left"],
			default: "Active",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "expires_within" && data) {
			// already expired: red, within 30 days: orange
			if (data.expires_within < 0) value = `<span style="color: var(--red-600)">${value}</span>`;
			else if (data.expires_within <= 30) value = `<span style="color: var(--orange-600)">${value}</span>`;
		}
		return value;
	},
};
