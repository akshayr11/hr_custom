# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Gratuity of employees as on a date, with the same calculation as EOS Statement, plus gratuity
advance and leave salary (one row per employee, like the old 'Gratuity Details' sheet)."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

from hr_custom.hr_custom.doctype.eos_statement.eos_statement import (
	calculate_gratuity,
	get_ineligibility_reasons,
)
from hr_custom.overrides.salary_structure_assignment import AIRFARE_COMPONENT
from hr_custom.utils import EMPLOYEE_LOCATION_FIELD, get_employee_category, get_nationality_field

# leave salary per day = basic / 30
LEAVE_SALARY_DAYS_IN_MONTH = 30
# Employee fields that may hold the ID (civil ID) number, in order of preference
ID_FIELDS = ("custom_civil_id", "civil_id", "custom_id_no", "id_no", "custom_civil_id_no", "national_id")

# (column key, basic type, rate) for the gratuity buckets
BUCKETS = [
	("half_fixed", "Freeze", "Half", "Half Fixed Basic"),
	("full_fixed", "Freeze", "Full", "Full Fixed Basic"),
	("half_current", "Current", "Half", "Half Current Basic"),
	("full_current", "Current", "Full", "Full Current Basic"),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.as_on_date:
		frappe.throw(_("Please set Company and As on Date"))
	return get_columns(), get_data(filters)


def get_columns():
	def col(label, fieldname, fieldtype="Data", width=110, **kw):
		return {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width, **kw}

	def money(label, fieldname, width=110):
		return col(label, fieldname, "Currency", width, options="currency")

	columns = [
		col("Emp No", "employee", "Link", 120, options="Employee"),
		col("Name", "employee_name", width=170),
		col("ID No", "id_no"),
		col("Position", "designation", "Link", 150, options="Designation"),
		col("Location", "location"),
		col("Department", "department", "Link", 130, options="Department"),
		col("Nationality", "nationality", width=100),
		money("Basic Salary", "basic_salary"),
		money("Total Allowance", "total_allowance"),
		money("Fixed Basic", "fixed_basic"),
		col("Fixed Basic Till Date", "fixed_basic_till", "Date"),
		col("As on Date", "as_on_date", "Date", 100),
		col("Date of Join", "date_of_joining", "Date", 100),
		col("Total No of Days", "total_days", "Int", 100),
	]
	for key, _basic, _rate, label in BUCKETS:
		columns.append(col(f"{label} Days", f"{key}_days", "Int", 100))
		columns.append(money(f"Gratuity on {label}", f"{key}_amount", 130))
	columns += [
		money("Total Gratuity", "total_gratuity", 120),
		money("Gratuity Advance", "gratuity_advance"),
		col("Leave Days", "leave_days", "Float", 90),
		money("Leave Salary", "leave_salary"),
		money("Grand Total", "grand_total", 120),
		col("Remarks", "remarks", width=250),
		col("Currency", "currency", "Link", 80, options="Currency", hidden=1),
	]
	return columns


def get_data(filters):
	as_on = getdate(filters.as_on_date)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	employees = get_employees(filters)
	annual_leave = get_annual_leave_type()
	advances = get_gratuity_advances([d.name for d in employees], as_on)

	data = []
	for emp in employees:
		category = emp.get("employee_category") or get_employee_category(emp.nationality)
		if filters.employee_category in ("Expat", "Omani") and category != filters.employee_category:
			continue

		total_days = date_diff(as_on, emp.date_of_joining) + 1
		row = frappe._dict(
			employee=emp.name,
			employee_name=emp.employee_name,
			id_no=emp.id_no,
			designation=emp.designation,
			location=emp.location,
			department=emp.department,
			nationality=emp.nationality,
			as_on_date=as_on,
			date_of_joining=emp.date_of_joining,
			total_days=total_days,
			currency=currency,
		)

		remarks = get_ineligibility_reasons(category, total_days)
		salary = get_salary_breakdown(emp.name, as_on)
		if salary:
			row.basic_salary, row.total_allowance = salary
		else:
			remarks.append(_("No Salary Structure assigned on {0}.").format(frappe.format(as_on, "Date")))

		if not remarks:
			add_gratuity(row, emp, as_on)

		row.gratuity_advance = advances.get(emp.name, 0)
		if annual_leave and row.basic_salary:
			row.leave_days = get_leave_balance(emp.name, annual_leave, as_on)
			row.leave_salary = flt(row.basic_salary / LEAVE_SALARY_DAYS_IN_MONTH * row.leave_days, 3)

		row.grand_total = flt(flt(row.total_gratuity) - flt(row.gratuity_advance) + flt(row.leave_salary), 3)
		row.remarks = " ".join(remarks)
		if filters.eligible_only and remarks:
			continue
		data.append(row)

	return data


def add_gratuity(row, emp, as_on):
	result = calculate_gratuity(emp.name, emp.date_of_joining, as_on, current_basic=row.basic_salary)
	row.fixed_basic = result["freeze_basic"] or None
	row.fixed_basic_till = result["freeze_till_date"]

	for d in result["details"]:
		for key, basic_type, rate, _label in BUCKETS:
			if d["basic_type"] == _(basic_type) and d["rate"] == _(rate):
				row[f"{key}_days"] = flt(row.get(f"{key}_days")) + d["days"]
				row[f"{key}_amount"] = flt(row.get(f"{key}_amount")) + d["amount"]
	row.total_gratuity = flt(sum(flt(d["amount"]) for d in result["details"]), 3)


def get_employees(filters):
	meta = frappe.get_meta("Employee")
	nationality_field = get_nationality_field()
	location_field = EMPLOYEE_LOCATION_FIELD if meta.has_field(EMPLOYEE_LOCATION_FIELD) else "branch"
	id_field = next((f for f in ID_FIELDS if meta.has_field(f)), None)

	fields = ["name", "employee_name", "designation", "department", "date_of_joining", f"{location_field} as location"]
	if nationality_field:
		fields.append(f"{nationality_field} as nationality")
	if id_field:
		fields.append(f"{id_field} as id_no")
	if meta.has_field("employee_category"):
		fields.append("employee_category")

	conditions = {"company": filters.company, "date_of_joining": ("<=", filters.as_on_date)}
	if filters.employee:
		conditions["name"] = filters.employee
	else:
		conditions["status"] = "Active"
	if filters.department:
		conditions["department"] = filters.department

	return frappe.get_all("Employee", filters=conditions, fields=fields, order_by="name")


def get_salary_breakdown(employee, on_date):
	"""(basic, other fixed allowances) - full-month amounts of the structure assigned on the date."""
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
	from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
		get_assigned_salary_structure,
	)

	structure = get_assigned_salary_structure(employee, on_date)
	if not structure:
		return None

	basic_component = frappe.db.get_single_value("Employee Warning Settings", "basic_component")
	try:
		slip = make_salary_slip(structure, employee=employee, posting_date=on_date, for_preview=1)
	except Exception:
		frappe.clear_messages()
		return None

	basic = allowances = 0.0
	for d in slip.earnings:
		if d.statistical_component or d.do_not_include_in_total or d.salary_component == AIRFARE_COMPONENT:
			continue
		amount = flt(d.default_amount or d.amount)
		is_basic = d.salary_component == basic_component or (
			not basic_component and "basic" in d.salary_component.lower()
		)
		if is_basic:
			basic += amount
		else:
			allowances += amount
	return basic, allowances


def get_annual_leave_type():
	return frappe.db.get_value("Leave Type", {"leave_type_name": ("like", "%annual%")}, "name")


def get_leave_balance(employee, leave_type, on_date):
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	try:
		return flt(get_leave_balance_on(employee, leave_type, on_date))
	except Exception:
		frappe.clear_messages()
		return 0


def get_gratuity_advances(employees, as_on):
	"""Paid Employee Advances whose purpose mentions gratuity, less amounts returned."""
	if not employees or not frappe.db.exists("DocType", "Employee Advance"):
		return {}

	rows = frappe.get_all(
		"Employee Advance",
		filters={
			"employee": ("in", employees),
			"docstatus": 1,
			"posting_date": ("<=", as_on),
			"purpose": ("like", "%gratuity%"),
		},
		fields=["employee", "paid_amount", "return_amount"],
	)
	result = {}
	for d in rows:
		result[d.employee] = result.get(d.employee, 0) + flt(d.paid_amount) - flt(d.return_amount)
	return result
