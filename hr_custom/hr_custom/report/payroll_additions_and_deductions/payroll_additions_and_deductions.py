# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import calendar

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, getdate

from hr_custom.utils import (
	EMPLOYEE_LOCATION_FIELD,
	get_nationality_field,
	has_employee_location,
	salary_slip_cost_center,
)

ADDITIONS = ["Airfare", "Overtime", "Other Additions", "Leave Salary", "Increment", "Claim Amount"]
DEDUCTIONS = [
	"Leave Deduction",
	"Attendance Deduction",
	"Installment",
	"Warning Deduction",
	"Other Deductions",
	"PASI",
	"Sec Fund",
]
# earnings that are part of the fixed monthly salary
FIXED = ("Basic Salary", "Fixed Allowance")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.month or not cint(filters.year):
		frappe.throw(_("Please set Month and Year"))

	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	slips = get_salary_slips(filters)
	return get_columns(), get_data(slips, currency)


def key(column):
	return frappe.scrub(column)


def get_columns():
	def money(label, fieldname=None, **kw):
		return {
			"fieldname": fieldname or key(label),
			"label": _(label),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 115,
			**kw,
		}

	columns = [
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Emp Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 130},
		{"fieldname": "current_location", "label": _("Current Location"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "costing_location",
			"label": _("Costing Location"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 130,
		},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation", "width": 130},
		{"fieldname": "job_category", "label": _("Job Category"), "fieldtype": "Data", "width": 130},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 100},
		money("Basic Salary"),
		money("Total Allowance Amount", "fixed_allowance"),
		money("Fixed Gross Salary", "fixed_gross", bold=1),
	]
	columns += [money(label if label != "Airfare" else "Airfare Amount", key(label), addition=1) for label in ADDITIONS]
	columns += [money(label, key(label), deduction=1) for label in DEDUCTIONS]
	columns += [
		money("Net Salary", "net_salary", bold=1),
		money("Net Diff", "net_diff"),
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]
	return columns


def get_data(slips, currency):
	if not slips:
		return []

	classify = get_classifier()
	details = get_salary_details([d.salary_slip for d in slips])

	rows = {}
	for slip in slips:
		row = rows.get(slip.employee)
		if not row:
			row = rows[slip.employee] = frappe._dict(
				employee=slip.employee,
				employee_name=slip.employee_name,
				department=slip.department,
				current_location=slip.get("current_location"),
				costing_location=slip.costing_location,
				designation=slip.designation,
				job_category=slip.get("job_category"),
				nationality=slip.get("nationality"),
				currency=currency,
				**{f: 0.0 for f in ("basic_salary", "fixed_allowance", "net_salary")},
				**{key(c): 0.0 for c in ADDITIONS + DEDUCTIONS},
			)
		add_slip(row, slip, details.get(slip.salary_slip, []), classify)

	data = []
	for row in sorted(rows.values(), key=lambda r: r.employee):
		row.fixed_gross = row.basic_salary + row.fixed_allowance
		row.net_diff = row.fixed_gross - row.net_salary
		data.append(row)
	return data


def add_slip(row, slip, components, classify):
	proration_loss = 0.0
	for d in components:
		column = classify(d)
		if d.parentfield == "earnings" and column in FIXED:
			# fixed salary at its full monthly value; what unpaid leave / absence took off is
			# shown as Leave / Attendance Deduction
			row[key(column)] += flt(d.default_amount or d.amount)
			proration_loss += flt(d.default_amount or d.amount) - flt(d.amount)
		else:
			row[key(column)] += flt(d.amount)

	# HRMS reduces the earnings themselves for unpaid days; split that loss by leave vs absence
	if proration_loss:
		lwp, absent = flt(slip.leave_without_pay), flt(slip.absent_days)
		leave_share = lwp / (lwp + absent) if (lwp + absent) else 0
		row.leave_deduction += proration_loss * leave_share
		row.attendance_deduction += proration_loss * (1 - leave_share)

	# loan installments are deducted outside the deductions table
	row.installment += flt(slip.get("total_loan_repayment"))
	row.net_salary += flt(slip.net_pay)


def get_classifier():
	"""Returns fn(salary_detail_row) -> report column. Payroll Report Settings mapping wins, then
	well-known components, then the component name."""
	mapping = {
		d.salary_component: d.report_column
		for d in frappe.get_all(
			"Payroll Report Component",
			filters={"parenttype": "Payroll Report Settings"},
			fields=["salary_component", "report_column"],
		)
	}
	basic = frappe.db.get_single_value("Employee Warning Settings", "basic_component")
	warning = frappe.db.get_single_value("Employee Warning Settings", "deduction_component")
	overtime = set(get_overtime_components())
	abbrs = dict(frappe.get_all("Salary Component", fields=["name", "salary_component_abbr"], as_list=True))

	def classify(d):
		component = d.salary_component
		if component in mapping:
			return mapping[component]
		text = f"{component} {abbrs.get(component) or ''}".lower()

		if d.parentfield == "earnings":
			if component == basic or (not basic and "basic" in text):
				return "Basic Salary"
			if "airfare" in text or "air fare" in text or "air ticket" in text:
				return "Airfare"
			if component in overtime or "overtime" in text or "over time" in text:
				return "Overtime"
			if "leave salary" in text or "leave encash" in text or "leave pay" in text:
				return "Leave Salary"
			if "increment" in text or "arrear" in text:
				return "Increment"
			if "claim" in text or "reimburse" in text or "expense" in text:
				return "Claim Amount"
			# one-off Additional Salary rows are additions; the rest is the fixed salary
			return "Other Additions" if d.additional_salary else "Fixed Allowance"

		if "pasi" in text:
			return "PASI"
		if "security fund" in text or "social security" in text or "sec fund" in text or "ssf" in text.split():
			return "Sec Fund"
		if component == warning:
			return "Warning Deduction"
		if "loan" in text or "install" in text or "advance" in text:
			return "Installment"
		if "leave" in text:
			return "Leave Deduction"
		if "absent" in text or "attendance" in text or "late" in text:
			return "Attendance Deduction"
		return "Other Deductions"

	return classify


def get_overtime_components():
	components = frappe.get_all("Salary Component", filters={"is_overtime_component": 1}, pluck="name") if frappe.get_meta(
		"Salary Component"
	).has_field("is_overtime_component") else []
	if frappe.db.exists("DocType", "Overtime Type"):
		components += frappe.get_all(
			"Overtime Type", filters={"overtime_salary_component": ("is", "set")}, pluck="overtime_salary_component"
		)
	return components


def get_salary_details(salary_slips):
	sd = frappe.qb.DocType("Salary Detail")
	rows = (
		frappe.qb.from_(sd)
		.select(
			sd.parent,
			sd.parentfield,
			sd.salary_component,
			sd.amount,
			sd.default_amount,
			sd.additional_salary,
		)
		.where(
			(sd.parenttype == "Salary Slip")
			& (sd.parent.isin(salary_slips))
			& (sd.statistical_component == 0)
			& (sd.do_not_include_in_total == 0)
		)
		.orderby(sd.idx)
	).run(as_dict=True)

	details = {}
	for d in rows:
		details.setdefault(d.parent, []).append(d)
	return details


def get_salary_slips(filters):
	month = list(calendar.month_name).index(filters.month)
	start = getdate(f"{cint(filters.year)}-{month:02d}-01")
	end = get_last_day(start)

	ss = frappe.qb.DocType("Salary Slip")
	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	pe = frappe.qb.DocType("Payroll Entry")
	costing = salary_slip_cost_center(pe, emp, dept)

	query = (
		frappe.qb.from_(ss)
		.join(emp)
		.on(ss.employee == emp.name)
		.left_join(dept)
		.on(emp.department == dept.name)
		.left_join(pe)
		.on(ss.payroll_entry == pe.name)
		.select(
			ss.name.as_("salary_slip"),
			ss.employee,
			emp.employee_name,
			emp.department,
			emp.designation,
			costing.as_("costing_location"),
			ss.net_pay,
			ss.leave_without_pay,
			ss.absent_days,
		)
		.where(
			(ss.docstatus == 1)
			& (ss.company == filters.company)
			& (ss.start_date >= start)
			& (ss.start_date <= end)
		)
	)

	meta = frappe.get_meta("Employee")
	if meta.has_field("job_category"):
		query = query.select(emp.job_category)
	nationality = get_nationality_field()
	if nationality:
		query = query.select(emp[nationality].as_("nationality"))
	if has_employee_location():
		query = query.select(emp[EMPLOYEE_LOCATION_FIELD].as_("current_location"))
	if frappe.get_meta("Salary Slip").has_field("total_loan_repayment"):
		query = query.select(ss.total_loan_repayment)

	if filters.location:
		if not has_employee_location():
			frappe.throw(_("Employee has no Employee Location field, so Location cannot be filtered."))
		query = query.where(emp[EMPLOYEE_LOCATION_FIELD] == filters.location)

	if filters.payroll_cost_center:
		cost_centers = [
			filters.payroll_cost_center,
			*(frappe.db.get_descendants("Cost Center", filters.payroll_cost_center) or []),
		]
		query = query.where(costing.isin(cost_centers))

	return query.run(as_dict=True)
