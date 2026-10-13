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


# Employee Location ("Current Location" in reports) - the site's own custom field
EMPLOYEE_LOCATION_FIELD = "custom_employee_location"


def has_employee_location():
	return frappe.get_meta("Employee").has_field(EMPLOYEE_LOCATION_FIELD)


def salary_slip_cost_center(payroll_entry, employee, department):
	"""Query term: cost center a salary slip belongs to - its Payroll Entry's Payroll Cost Center,
	else the employee's (or their department's) payroll cost center. Same rule as Bank Letter."""
	cost_center = employee_payroll_cost_center(employee, department)
	if frappe.get_meta("Payroll Entry").has_field("payroll_cost_center"):
		cost_center = Coalesce(NullIf(payroll_entry.payroll_cost_center, ""), cost_center)
	return cost_center


def get_salary_slips_for_report(filters, fields=()):
	"""Submitted salary slips of `filters.company` for `filters.year`, filtered by Location (Employee
	Location) and Payroll Cost Center. `fields` are extra Employee fields to select (skipped if the
	site doesn't have them). Each row has employee, salary_slip, start_date, amount (gross/net)."""
	from frappe.utils import cint

	year = cint(filters.year)
	ss = frappe.qb.DocType("Salary Slip")
	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	pe = frappe.qb.DocType("Payroll Entry")
	amount = ss.net_pay if filters.get("amount_based_on") == "Net Pay" else ss.gross_pay

	query = (
		frappe.qb.from_(ss)
		.join(emp)
		.on(ss.employee == emp.name)
		.left_join(dept)
		.on(emp.department == dept.name)
		.left_join(pe)
		.on(ss.payroll_entry == pe.name)
		.select(ss.name.as_("salary_slip"), ss.employee, ss.start_date, amount.as_("amount"))
		.where(
			(ss.docstatus == 1)
			& (ss.company == filters.company)
			& (ss.start_date >= f"{year}-01-01")
			& (ss.start_date <= f"{year}-12-31")
		)
	)

	meta = frappe.get_meta("Employee")
	for fieldname in fields:
		if meta.has_field(fieldname) or fieldname in ("employee_name", "department", "designation", "date_of_joining"):
			query = query.select(emp[fieldname])

	if filters.get("location"):
		if not has_employee_location():
			frappe.throw(frappe._("Employee has no Employee Location field, so Location cannot be filtered."))
		query = query.where(emp[EMPLOYEE_LOCATION_FIELD] == filters.location)

	if filters.get("payroll_cost_center"):
		cost_centers = [
			filters.payroll_cost_center,
			*(frappe.db.get_descendants("Cost Center", filters.payroll_cost_center) or []),
		]
		query = query.where(salary_slip_cost_center(pe, emp, dept).isin(cost_centers))

	return query.run(as_dict=True)
