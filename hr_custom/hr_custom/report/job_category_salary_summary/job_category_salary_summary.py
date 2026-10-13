# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import calendar

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from hr_custom.utils import get_salary_slips_for_report

MONTHS = [calendar.month_abbr[m] for m in range(1, 13)]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not cint(filters.year):
		frappe.throw(_("Please set Year"))

	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	return get_columns(), get_data(filters, currency)


def get_columns():
	columns = [
		{"fieldname": "job_category", "label": _("Job Category"), "fieldtype": "Data", "width": 180},
	]
	for month in MONTHS:
		key = month.lower()
		columns += [
			{"fieldname": f"{key}_count", "label": _("{0} Emp Count").format(_(month)), "fieldtype": "Int", "width": 90},
			{
				"fieldname": f"{key}_total",
				"label": _("{0} Total Sal").format(_(month)),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
		]
	columns += [
		{
			"fieldname": "year_total",
			"label": _("Year Total Sal"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]
	return columns


def get_data(filters, currency):
	not_set = _("Not Set")
	summary = {}  # job category -> month -> {"employees": set, "total": float}

	for slip in get_salary_slips(filters):
		month = getdate(slip.start_date).month
		cell = summary.setdefault(slip.get("job_category") or not_set, {}).setdefault(
			month, {"employees": set(), "total": 0.0}
		)
		cell["employees"].add(slip.employee)
		cell["total"] += flt(slip.amount)

	# "Not Set" at the end, others alphabetically
	categories = sorted(summary, key=lambda c: (c == not_set, c.lower()))

	data = []
	for category in categories:
		row = {"job_category": category, "currency": currency, "year_total": 0.0}
		for number, month in enumerate(MONTHS, start=1):
			cell = summary[category].get(number)  # months without payroll stay 0
			key = month.lower()
			row[f"{key}_count"] = len(cell["employees"]) if cell else 0
			row[f"{key}_total"] = cell["total"] if cell else 0.0
			row["year_total"] += row[f"{key}_total"]
		data.append(row)

	return data


def get_salary_slips(filters):
	return get_salary_slips_for_report(filters, fields=["job_category"])
