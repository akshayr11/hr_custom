import frappe
from frappe.query_builder.functions import Coalesce, NullIf

EMPLOYEE_CATEGORIES = ("Omani", "Expat")
# lower-cased nationality values that count as Omani
OMANI_NATIONALITIES = ("oman", "omani")
# Employee field holding nationality, in order of preference (custom_nationality is the site's own field)
NATIONALITY_FIELDS = ("custom_nationality", "nationality")


def get_nationality_field():
	meta = frappe.get_meta("Employee")
	for fieldname in NATIONALITY_FIELDS:
		if meta.has_field(fieldname):
			return fieldname


def has_job_category():
	return frappe.get_meta("Employee").has_field("job_category")


def has_employee_category():
	# created by `bench migrate` (hr_custom.setup); guard so payroll still works before that
	return frappe.get_meta("Employee").has_field("employee_category")


def get_employee_category(nationality):
	if not nationality:
		return None
	return "Omani" if nationality.strip().lower() in OMANI_NATIONALITIES else "Expat"


def set_employee_category(doc, method=None):
	"""Employee validate hook: Employee Category follows Nationality."""
	fieldname = get_nationality_field()
	if fieldname:
		doc.employee_category = get_employee_category(doc.get(fieldname))


def employee_payroll_cost_center(employee, department):
	"""Query term: employee's payroll cost center, else their department's (same fallback as HRMS).
	`employee`/`department` are qb DocType objects; Department must be left-joined."""
	return Coalesce(NullIf(employee.payroll_cost_center, ""), department.payroll_cost_center)


def get_matching_employees(employees, employee_category=None, payroll_cost_center=None, job_category=None):
	"""Subset of `employees` matching the category ("All"/empty = any), job category and payroll
	cost center (including its child cost centers)."""
	if not employees:
		return set()

	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	query = (
		frappe.qb.from_(emp)
		.left_join(dept)
		.on(emp.department == dept.name)
		.select(emp.name)
		.where(emp.name.isin(list(employees)))
	)

	if employee_category in EMPLOYEE_CATEGORIES and has_employee_category():
		query = query.where(emp.employee_category == employee_category)

	if job_category and has_job_category():
		query = query.where(emp.job_category == job_category)

	if payroll_cost_center:
		cost_centers = [payroll_cost_center, *(frappe.db.get_descendants("Cost Center", payroll_cost_center) or [])]
		query = query.where(employee_payroll_cost_center(emp, dept).isin(cost_centers))

	return set(query.run(pluck=True))


def get_employee_payroll_details(employees):
	"""{employee: {employee_category, job_category, payroll_cost_center}}; cost center falls back to
	the department's."""
	if not employees:
		return {}

	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	query = (
		frappe.qb.from_(emp)
		.left_join(dept)
		.on(emp.department == dept.name)
		.select(emp.name, employee_payroll_cost_center(emp, dept).as_("payroll_cost_center"))
		.where(emp.name.isin(list(employees)))
	)
	if has_employee_category():
		query = query.select(emp.employee_category)
	if has_job_category():
		query = query.select(emp.job_category)

	return {d.name: d for d in query.run(as_dict=True)}
