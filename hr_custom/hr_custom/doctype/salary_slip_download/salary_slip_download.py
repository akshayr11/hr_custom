# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Download the salary slips of one or more employees for a range of months as a single PDF."""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_last_day, getdate

from hr_custom.hr_custom.doctype.bank_letter.bank_letter import MONTHS


class SalarySlipDownload(Document):
	pass


@frappe.whitelist()
def get_salary_slips(filters):
	"""Names of the salary slips (the user can read) matching the filters, by employee and month."""
	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else filters)
	for field in ("company", "from_month", "from_year", "to_month", "to_year"):
		if not filters.get(field):
			frappe.throw(_("Please set {0}").format(_(frappe.unscrub(field))))

	from_date = getdate(f"{cint(filters.from_year)}-{MONTHS.index(filters.from_month) + 1:02d}-01")
	to_date = get_last_day(f"{cint(filters.to_year)}-{MONTHS.index(filters.to_month) + 1:02d}-01")
	if from_date > to_date:
		frappe.throw(_("From Month cannot be after To Month"))

	conditions = {
		"company": filters.company,
		"start_date": ("between", [from_date, to_date]),
		"docstatus": ("in", [0, 1]) if cint(filters.include_draft) else 1,
	}
	employees = [d["employee"] if isinstance(d, dict) else d for d in filters.get("employees") or []]
	if employees:
		conditions["employee"] = ("in", employees)
	if filters.get("department"):
		conditions["department"] = filters.department

	return frappe.get_list(
		"Salary Slip",
		filters=conditions,
		pluck="name",
		order_by="employee_name asc, start_date asc",
		limit_page_length=0,
	)
