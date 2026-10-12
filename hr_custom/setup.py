from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	make_custom_fields()


def after_migrate():
	make_custom_fields()


def make_custom_fields():
	create_custom_fields(
		{
			"Cost Center": [
				{
					"fieldname": "is_head_office",
					"fieldtype": "Check",
					"label": "Is Head Office",
					"insert_after": "is_group",
					"description": "Bank Letter allows department wise selection for Head Office cost centers",
				}
			],
			"Employee": [
				{
					"fieldname": "employee_category",
					"fieldtype": "Select",
					"label": "Employee Category",
					"options": "\nOmani\nExpat",
					"insert_after": "employment_type",
					"in_standard_filter": 1,
				}
			],
			"Payroll Entry": [
				{
					"fieldname": "employee_category",
					"fieldtype": "Select",
					"label": "Employee Category",
					"options": "All\nOmani\nExpat",
					"default": "All",
					"insert_after": "grade",
				},
				{
					"fieldname": "payroll_cost_center",
					"fieldtype": "Link",
					"label": "Payroll Cost Center",
					"options": "Cost Center",
					"insert_after": "employee_category",
					"description": "Only employees whose Payroll Cost Center is this (or a child of it)",
				},
			],
			"Salary Component": [
				{
					"fieldname": "is_overtime_component",
					"fieldtype": "Check",
					"label": "Is Overtime (OT) Component",
					"insert_after": "depends_on_payment_days",
					"depends_on": "eval:doc.type=='Earning'",
					"description": "Used by Bank Letter to separate OT from salary",
				}
			],
		},
		update=True,
	)
