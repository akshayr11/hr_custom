# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee Payroll Comparison (Cost Center wise) between the selected month and the previous one.

* Employees in the selected month's payroll and not in the previous month's
* Employees in the previous month's payroll and not in the selected month's

An employee is in a month's payroll of a cost center when they have a submitted salary slip for
that month there that is not withheld. The reason is worked out from the employee's records:
transfer to / from another cost center, withheld salary, unsubmitted slip, joining, end of
service, status, leave or rejoining.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, formatdate, get_last_day, getdate

from hr_custom.utils import salary_slip_cost_center


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.month or not cint(filters.year):
		frappe.throw(_("Please set Month and Year"))

	month = list(calendar.month_name).index(filters.month)
	current = getdate(f"{cint(filters.year)}-{month:02d}-01")
	previous = add_months(current, -1)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	# all cost centers, so a transfer out of the filtered cost center is still found as the reason
	slips = {start: get_salary_slips(filters, start) for start in (current, previous)}
	cost_centers = get_cost_centers(filters)
	paid = {start: get_paid(slips[start], cost_centers) for start in slips}
	cur, prev = label(current), label(previous)

	data = []
	for title, present, missing in (
		(_("Employees in {0} Payroll and Not in {1} Payroll").format(cur, prev), current, previous),
		(_("Employees in {0} Payroll and Not in {1} Payroll").format(prev, cur), previous, current),
	):
		if data:
			data.append({})
		data.append({"cost_center": title, "is_heading": 1, "bold": 1})
		keys = sorted(set(paid[present]) - set(paid[missing]), key=lambda k: (k[1].lower(), k[0]))
		if not keys:
			data.append({"cost_center": _("None")})
			continue

		employees = get_employees({k[0] for k in keys})
		for employee, cost_center in keys:
			emp = employees.get(employee, frappe._dict())
			data.append(
				{
					"cost_center": cost_center,
					"employee": employee,
					"employee_name": emp.employee_name,
					"designation": emp.designation,
					"net_salary": paid[present][(employee, cost_center)],
					"reason": get_reason(emp, employee, cost_center, slips[missing], missing, present > missing),
					"currency": currency,
				}
			)
	return get_columns(), data


def label(start):
	return start.strftime("%b %Y")


def get_columns():
	return [
		{"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Data", "width": 200},
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Emp Full Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "designation", "label": _("Job Title"), "fieldtype": "Data", "width": 160},
		{"fieldname": "net_salary", "label": _("Net Salary"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 380},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_salary_slips(filters, start):
	"""Salary slips (draft and submitted) of the month, all cost centers, with the cost center name."""
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
		.select(ss.name, ss.employee, ss.docstatus, ss.status, ss.net_pay, cost_center.as_("cost_center"))
		.where(
			(ss.docstatus < 2)
			& (ss.company == filters.company)
			& (ss.start_date >= start)
			& (ss.start_date <= get_last_day(start))
		)
	)
	names = dict(frappe.get_all("Cost Center", fields=["name", "cost_center_name"], as_list=True))
	slips = query.run(as_dict=True)
	for slip in slips:
		slip.cost_center_id = slip.cost_center
		slip.cost_center = names.get(slip.cost_center) or slip.cost_center or _("Not Set")
	return slips


def get_cost_centers(filters):
	if filters.payroll_cost_center:
		return {
			filters.payroll_cost_center,
			*(frappe.db.get_descendants("Cost Center", filters.payroll_cost_center) or []),
		}


def get_paid(slips, cost_centers=None):
	"""(employee, cost center) -> net pay, for submitted slips that are not withheld."""
	paid = {}
	for slip in slips:
		if cost_centers is not None and slip.cost_center_id not in cost_centers:
			continue
		if slip.docstatus == 1 and slip.status != "Withheld":
			key = (slip.employee, slip.cost_center)
			paid[key] = paid.get(key, 0) + flt(slip.net_pay)
	return paid


def get_employees(employees):
	fields = ["name", "employee_name", "designation", "date_of_joining", "relieving_date", "status"]
	if frappe.get_meta("Employee").has_field("rejoin_date"):
		fields.append("rejoin_date")
	return {d.name: d for d in frappe.get_all("Employee", {"name": ("in", list(employees))}, fields)}


def get_reason(emp, employee, cost_center, other_slips, other_start, is_new):
	"""Why the employee has no paid slip in the cost center for the other month (`other_start`).
	`is_new`: the employee is in the selected month and missing from the previous one."""
	month = label(other_start)
	month_end = get_last_day(other_start)
	slips = [s for s in other_slips if s.employee == employee]

	elsewhere = [s for s in slips if s.cost_center != cost_center and s.docstatus == 1]
	if elsewhere:
		return (_("Transferred from {0}") if is_new else _("Transferred to {0}")).format(elsewhere[0].cost_center)

	withheld = [s for s in slips if s.docstatus == 1 and s.status == "Withheld"]
	if withheld or (not slips and get_withholding(employee, other_start)):
		reason = get_withholding(employee, other_start)
		return _("Salary withheld in {0}").format(month) + (f": {reason}" if reason else "")

	if any(s.docstatus == 0 for s in slips):
		return _("{0} salary slip not submitted").format(month)

	if is_new and emp.date_of_joining and getdate(emp.date_of_joining) > month_end:
		return _("New joining ({0})").format(formatdate(emp.date_of_joining))
	if not is_new and emp.relieving_date and getdate(emp.relieving_date) < other_start:
		return _("End of service (Relieving Date {0})").format(formatdate(emp.relieving_date))
	if not is_new and emp.status in ("Left", "Inactive", "Suspended"):
		return _("Employee status {0}").format(_(emp.status))

	leave = get_leave(employee, other_start, month_end)
	if leave:
		return _("On {0} in {1} ({2} to {3})").format(
			leave.leave_type, month, formatdate(leave.from_date), formatdate(leave.to_date)
		)
	if is_new and emp.get("rejoin_date") and getdate(emp.rejoin_date) > month_end:
		return _("Rejoined on {0}").format(formatdate(emp.rejoin_date))

	return _("No salary slip in {0}").format(month)


def get_withholding(employee, start):
	"""Reason of a submitted Salary Withholding covering the month ('' when there is none)."""
	if not frappe.db.exists("DocType", "Salary Withholding"):
		return None
	withholding = frappe.db.get_value(
		"Salary Withholding",
		{
			"employee": employee,
			"docstatus": 1,
			"from_date": ("<=", get_last_day(start)),
			"to_date": (">=", start),
		},
		["name", "reason_for_withholding_salary"],
		as_dict=True,
	)
	if withholding:
		return withholding.reason_for_withholding_salary or withholding.name
	return None


def get_leave(employee, start, end):
	return frappe.db.get_value(
		"Leave Application",
		{
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ("<=", end),
			"to_date": (">=", start),
		},
		["leave_type", "from_date", "to_date"],
		as_dict=True,
		order_by="from_date",
	)
