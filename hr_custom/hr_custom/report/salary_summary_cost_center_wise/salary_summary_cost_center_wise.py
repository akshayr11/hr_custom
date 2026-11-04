# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Salary Summary (Cost Center wise): per payroll cost center, the employee count and salary of
Omani and Expat employees with their OT and Leave Salary, plus Air Fare, for the selected month
and, below it, the previous month.

Salary is the gross pay of the submitted salary slips; OT / Air Fare / Leave Salary are the
earnings classified as such (Payroll Report Settings mapping, as in Payroll Additions and
Deductions) and are part of that gross.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_last_day, getdate

from hr_custom.hr_custom.report.payroll_additions_and_deductions.payroll_additions_and_deductions import (
	get_classifier,
	get_salary_details,
)
from hr_custom.utils import get_employee_category, get_nationality_field, has_employee_category, salary_slip_cost_center

GROUPS = (("omn", "OMN"), ("exp", "EXP"))
EARNING_COLUMNS = {"Overtime": "ot", "Leave Salary": "leave_salary", "Airfare": "air_fare"}
AMOUNT_FIELDS = (
	"salary_omn",
	"ot_omn",
	"leave_salary_omn",
	"salary_exp",
	"ot_exp",
	"leave_salary_exp",
	"total_ot",
	"total_air_fare",
	"total_leave_salary",
	"total_salary",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.month or not cint(filters.year):
		frappe.throw(_("Please set Month and Year"))

	month = list(calendar.month_name).index(filters.month)
	current = getdate(f"{cint(filters.year)}-{month:02d}-01")
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	data = []
	for start in (current, add_months(current, -1)):
		if data:
			data.append({})
		data += get_month_rows(filters, start, currency)
	return get_columns(), data


def get_columns():
	def money(fieldname, label, width=120):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "options": "currency", "width": width}

	def count(fieldname, label):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Int", "width": 90}

	return [
		{"fieldname": "location", "label": _("Loc Name"), "fieldtype": "Data", "width": 200},
		count("emp_omn", _("Tot Emp OMN")),
		money("salary_omn", _("Salary OMN")),
		money("ot_omn", _("OT Amt OMN")),
		money("leave_salary_omn", _("Leave Sal OMN")),
		count("emp_exp", _("Tot Emp EXP")),
		money("salary_exp", _("Salary EXP")),
		money("ot_exp", _("OT Amt EXP")),
		money("leave_salary_exp", _("Leave Sal EXP")),
		money("total_ot", _("Total OT Amt")),
		money("total_air_fare", _("Total Air Fare")),
		money("total_leave_salary", _("Total Leave Salary")),
		money("total_salary", _("Total Salary"), 140),
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_month_rows(filters, start, currency):
	title = start.strftime("%B %Y")
	heading = {"location": title, "is_heading": 1, "bold": 1, "currency": currency}
	slips = get_salary_slips(filters, start)
	if not slips:
		return [heading, {"location": _("No submitted salary slips"), "currency": currency}]

	classify = get_classifier()
	details = get_salary_details([d.salary_slip for d in slips])
	names = dict(frappe.get_all("Cost Center", fields=["name", "cost_center_name"], as_list=True))

	rows = {}
	for slip in slips:
		cost_center = slip.cost_center or ""
		row = rows.get(cost_center)
		if not row:
			row = rows[cost_center] = new_row(names.get(cost_center) or cost_center or _("Not Set"), currency)
			row.cost_center = cost_center
			row.employees = {"omn": set(), "exp": set()}

		group = "omn" if get_category(slip) == "Omani" else "exp"
		row.employees[group].add(slip.employee)
		row[f"salary_{group}"] += flt(slip.gross_pay)
		for d in details.get(slip.salary_slip, []):
			column = EARNING_COLUMNS.get(classify(d)) if d.parentfield == "earnings" else None
			if column == "air_fare":
				row.total_air_fare += flt(d.amount)
			elif column:
				row[f"{column}_{group}"] += flt(d.amount)

	total = new_row(_("Total {0}").format(title), currency)
	total.bold = 1
	data = [heading]
	for row in sorted(rows.values(), key=lambda r: r.location.lower()):
		row.emp_omn, row.emp_exp = len(row.employees["omn"]), len(row.employees["exp"])
		del row["employees"]
		row.total_ot = row.ot_omn + row.ot_exp
		row.total_leave_salary = row.leave_salary_omn + row.leave_salary_exp
		row.total_salary = row.salary_omn + row.salary_exp
		for field in ("emp_omn", "emp_exp", *AMOUNT_FIELDS):
			total[field] += row[field]
		data.append(row)
	data.append(total)
	return data


def new_row(location, currency):
	return frappe._dict(location=location, currency=currency, emp_omn=0, emp_exp=0, **{f: 0.0 for f in AMOUNT_FIELDS})


def get_category(slip):
	# employees without a nationality are counted as Expat
	return slip.get("employee_category") or get_employee_category(slip.get("nationality"))


def get_salary_slips(filters, start):
	ss = frappe.qb.DocType("Salary Slip")
	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	pe = frappe.qb.DocType("Payroll Entry")
	cost_center = salary_slip_cost_center(pe, emp, dept)

	query = (
		frappe.qb.from_(ss)
		.join(emp)
		.on(ss.employee == emp.name)
		.left_join(dept)
		.on(emp.department == dept.name)
		.left_join(pe)
		.on(ss.payroll_entry == pe.name)
		.select(ss.name.as_("salary_slip"), ss.employee, ss.gross_pay, cost_center.as_("cost_center"))
		.where(
			(ss.docstatus == 1)
			& (ss.company == filters.company)
			& (ss.start_date >= start)
			& (ss.start_date <= get_last_day(start))
		)
	)
	if has_employee_category():
		query = query.select(emp.employee_category)
	nationality = get_nationality_field()
	if nationality:
		query = query.select(emp[nationality].as_("nationality"))

	if filters.payroll_cost_center:
		cost_centers = [
			filters.payroll_cost_center,
			*(frappe.db.get_descendants("Cost Center", filters.payroll_cost_center) or []),
		]
		query = query.where(cost_center.isin(cost_centers))

	return query.run(as_dict=True)
