import frappe
from frappe.query_builder.functions import Coalesce, NullIf

EMPLOYEE_CATEGORIES = ("Omani", "Expat")


def employee_payroll_cost_center(employee, department):
	"""Query term: employee's payroll cost center, else their department's (same fallback as HRMS).
	`employee`/`department` are qb DocType objects; Department must be left-joined."""
	return Coalesce(NullIf(employee.payroll_cost_center, ""), department.payroll_cost_center)


def get_matching_employees(employees, employee_category=None, payroll_cost_center=None):
	"""Subset of `employees` matching the category ("All"/empty = any) and payroll cost center
	(including its child cost centers)."""
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

	if employee_category in EMPLOYEE_CATEGORIES:
		query = query.where(emp.employee_category == employee_category)

	if payroll_cost_center:
		cost_centers = [payroll_cost_center, *(frappe.db.get_descendants("Cost Center", payroll_cost_center) or [])]
		query = query.where(employee_payroll_cost_center(emp, dept).isin(cost_centers))

	return set(query.run(pluck=True))
