# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Frozen basic salary of an employee: gratuity for service up to the Till Date is calculated on
this basic, the remaining service on the current basic (see EOS Statement)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class EmployeeFreezeBasic(Document):
	def validate(self):
		if flt(self.freeze_basic) <= 0:
			frappe.throw(_("Freeze Basic must be greater than 0"))
		if self.date_of_joining and getdate(self.till_date) < getdate(self.date_of_joining):
			frappe.throw(_("Till Date cannot be before the Date of Joining"))

		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.current_basic = get_current_basic_or_zero(self.employee, nowdate())
		self.validate_duplicate()

	def validate_duplicate(self):
		other = frappe.db.get_value(
			"Employee Freeze Basic",
			{"employee": self.employee, "docstatus": 1, "name": ("!=", self.name)},
		)
		if other:
			frappe.throw(
				_("Employee {0} already has Freeze Basic {1}. Cancel or amend it instead.").format(
					frappe.bold(self.employee_name or self.employee), frappe.bold(other)
				)
			)


def get_freeze_basic(employee):
	"""The employee's submitted Freeze Basic, if any."""
	return frappe.db.get_value(
		"Employee Freeze Basic",
		{"employee": employee, "docstatus": 1},
		["name", "freeze_basic", "till_date"],
		as_dict=True,
	)


def get_current_basic_or_zero(employee, on_date):
	from hr_custom.hr_custom.doctype.eos_statement.eos_statement import get_current_basic

	try:
		return get_current_basic(employee, on_date)
	except frappe.ValidationError:
		frappe.clear_messages()
		return 0
