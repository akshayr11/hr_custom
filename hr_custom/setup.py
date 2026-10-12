import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def after_install():
	make_custom_fields()


def after_migrate():
	make_custom_fields()


def make_custom_fields():
	from hr_custom.utils import get_nationality_field

	make_nationality_field()
	nationality_field = get_nationality_field()
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
					"insert_after": nationality_field,
					"in_standard_filter": 1,
					"read_only": 1,
					"description": "Set from Nationality: Oman = Omani, any other = Expat",
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
			"Payroll Employee Detail": [
				{
					"fieldname": "employee_category",
					"fieldtype": "Data",
					"label": "Employee Category",
					"fetch_from": "employee.employee_category",
					"insert_after": "designation",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 1,
				},
				{
					"fieldname": "payroll_cost_center",
					"fieldtype": "Link",
					"label": "Payroll Cost Center",
					"options": "Cost Center",
					"fetch_from": "employee.payroll_cost_center",
					"insert_after": "employee_category",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 2,
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
	make_job_category_fields()
	make_property_setters()
	update_employee_categories()


def make_nationality_field():
	from hr_custom.utils import get_nationality_field

	# use the site's own nationality field (e.g. custom_nationality) if there is one
	if get_nationality_field():
		return

	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "nationality",
					"fieldtype": "Link",
					"label": "Nationality",
					"options": "Country",
					"insert_after": "employment_type",
					"in_standard_filter": 1,
				}
			]
		}
	)


def make_job_category_fields():
	"""Job Category filter/column in Payroll Entry, mirroring Employee.job_category (if the site has it)."""
	df = frappe.get_meta("Employee").get_field("job_category")
	if not df:
		return

	fieldtype = df.fieldtype if df.fieldtype in ("Link", "Select") else "Data"
	options = df.options if fieldtype != "Data" else None
	create_custom_fields(
		{
			"Payroll Entry": [
				{
					"fieldname": "job_category",
					"fieldtype": fieldtype,
					"options": options,
					"label": "Job Category",
					"insert_after": "employee_category",
				}
			],
			"Payroll Employee Detail": [
				{
					"fieldname": "job_category",
					"fieldtype": fieldtype,
					"options": options,
					"label": "Job Category",
					"fetch_from": "employee.job_category",
					"insert_after": "employee_category",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 2,
				}
			],
		},
		update=True,
	)


def update_employee_categories():
	"""Backfill Employee Category from Nationality for existing employees."""
	from frappe.query_builder import Case
	from frappe.query_builder.functions import Lower, Trim

	from hr_custom.utils import OMANI_NATIONALITIES, get_nationality_field

	fieldname = get_nationality_field()
	if not fieldname:
		return

	employee = frappe.qb.DocType("Employee")
	nationality_value = employee[fieldname]
	nationality = Lower(Trim(nationality_value))
	category = (
		Case()
		.when(nationality_value.isnull() | (nationality_value == ""), None)
		.when(nationality.isin(OMANI_NATIONALITIES), "Omani")
		.else_("Expat")
	)
	frappe.qb.update(employee).set(employee.employee_category, category).run()


def make_property_setters():
	# make room for Employee Category / Job Category / Payroll Cost Center in Payroll Entry's employee
	# grid (10 columns): Employee 2, Name 2, Category 1, Job Category 2, Cost Center 2, Withheld 1
	setters = [
		("designation", "in_list_view", 0, "Check"),
		("is_salary_withheld", "columns", 1, "Int"),
		("employee_name", "columns", 2, "Int"),
	]
	if frappe.get_meta("Employee").has_field("job_category"):
		setters.append(("department", "in_list_view", 0, "Check"))
	for fieldname, prop, value, property_type in setters:
		make_property_setter(
			"Payroll Employee Detail", fieldname, prop, value, property_type, validate_fields_for_doctype=False
		)
