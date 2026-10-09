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
