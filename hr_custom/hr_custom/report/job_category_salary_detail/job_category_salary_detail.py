# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import calendar

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from hr_custom.utils import (
	EMPLOYEE_LOCATION_FIELD,
	get_employee_payroll_details,
	get_nationality_field,
	get_salary_slips_for_report,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not cint(filters.year):
		frappe.throw(_("Please set Year"))

	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	nationality_field = get_nationality_field()
	slips = get_salary_slips_for_report(
		filters,
		fields=[
			"employee_name",
			"department",
			"designation",
			"date_of_joining",
			"job_category",
			EMPLOYEE_LOCATION_FIELD,
			*([nationality_field] if nationality_field else []),
		],
	)

	# only months in which payroll was run get a column
	months = sorted({getdate(d.start_date).month for d in slips})
	return get_columns(months), get_data(slips, months, currency, nationality_field)


def get_columns(months):
	columns = [
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Emp Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 140},
		{"fieldname": "current_location", "label": _("Current Location"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "mkz_costing",
			"label": _("MKZ Costing"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 130,
		},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation", "width": 140},
		{"fieldname": "job_category", "label": _("Job Category"), "fieldtype": "Data", "width": 140},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 110},
		{"fieldname": "date_of_joining", "label": _("Join Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "gross_salary",
			"label": _("Gross Salary"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
	]
	for month in months:
		columns.append(
			{
				"fieldname": f"{calendar.month_abbr[month].lower()}_total",
				"label": _("{0} Total Sal").format(_(calendar.month_abbr[month])),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			}
		)
	columns += [
		{"fieldname": "year_total", "label": _("Year Total Sal"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]
	return columns


def get_data(slips, months, currency, nationality_field):
	not_set = _("Not Set")
	rows = {}
	latest_slip = {}  # employee -> (start_date, salary_slip) for Gross Salary

	for slip in slips:
		row = rows.get(slip.employee)
		if not row:
			row = rows[slip.employee] = frappe._dict(
				employee=slip.employee,
				employee_name=slip.employee_name,
				department=slip.department,
				current_location=slip.get(EMPLOYEE_LOCATION_FIELD),
				designation=slip.designation,
				job_category=slip.get("job_category") or not_set,
				nationality=slip.get(nationality_field) if nationality_field else None,
				date_of_joining=slip.date_of_joining,
				currency=currency,
				year_total=0.0,
				**{f"{calendar.month_abbr[m].lower()}_total": 0.0 for m in months},
			)
		key = f"{calendar.month_abbr[getdate(slip.start_date).month].lower()}_total"
		row[key] += flt(slip.amount)
		row.year_total += flt(slip.amount)

		start = getdate(slip.start_date)
		if slip.employee not in latest_slip or start > latest_slip[slip.employee][0]:
			latest_slip[slip.employee] = (start, slip.salary_slip)

	# MKZ Costing = employee's Payroll Cost Center (else their department's)
	details = get_employee_payroll_details(list(rows))
	gross = get_full_month_gross([d[1] for d in latest_slip.values()])
	for employee, row in rows.items():
		row.mkz_costing = (details.get(employee) or {}).get("payroll_cost_center")
		row.gross_salary = gross.get(latest_slip[employee][1], 0.0)

	# grouped job category wise; "Not Set" last
	return sorted(
		rows.values(),
		key=lambda r: (r.job_category == not_set, r.job_category.lower(), r.employee),
	)


def get_full_month_gross(salary_slips):
	"""{salary_slip: gross} - unprorated monthly earnings of the slip, leaving out one-off
	Additional Salary (OT, bonus, ...) and statistical / not-in-total components."""
	if not salary_slips:
		return {}

	sd = frappe.qb.DocType("Salary Detail")
	rows = (
		frappe.qb.from_(sd)
		.select(sd.parent, frappe.query_builder.functions.Sum(sd.default_amount))
		.where(
			(sd.parenttype == "Salary Slip")
			& (sd.parentfield == "earnings")
			& (sd.parent.isin(salary_slips))
			& (sd.statistical_component == 0)
			& (sd.do_not_include_in_total == 0)
			& (sd.additional_salary.isnull() | (sd.additional_salary == ""))
		)
		.groupby(sd.parent)
	).run()
	return {d[0]: flt(d[1]) for d in rows}
