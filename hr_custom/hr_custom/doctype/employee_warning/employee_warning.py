# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, get_first_day, get_last_day, getdate

ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]


class EmployeeWarning(Document):
	def validate(self):
		self.validate_dates()
		self.set_warning_number()
		self.set_currency()
		if self.action == "Deduction":
			self.calculate_deduction()
		else:
			self.no_of_days = self.basic = self.per_day_basic = self.amount = 0

	def before_submit(self):
		if self.status not in ("Approved", "Rejected"):
			frappe.throw(_("Only Employee Warnings with status 'Approved' or 'Rejected' can be submitted"))
		# other warnings may have been approved since this one was drafted
		self.set_warning_number()

	def on_submit(self):
		if self.status == "Approved" and self.action == "Deduction":
			self.create_additional_salary()

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		if self.additional_salary:
			additional_salary = frappe.get_doc("Additional Salary", self.additional_salary)
			if additional_salary.docstatus == 1:
				additional_salary.cancel()

	def validate_dates(self):
		if self.date_of_joining and getdate(self.effective_date) < getdate(self.date_of_joining):
			frappe.throw(_("Effective Date cannot be before the employee's Join Date"))

	def set_warning_number(self):
		previous = len(get_warning_history(self.employee, self.name))
		self.warning_number = previous + 1
		self.warning_level = get_warning_level(self.warning_number)

	def set_currency(self):
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def calculate_deduction(self):
		if flt(self.no_of_days) <= 0:
			frappe.throw(_("No Of Days must be greater than 0 for a Deduction"))

		settings = frappe.get_cached_doc("Employee Warning Settings")
		self.basic = get_basic_salary(self.employee, self.effective_date, settings.basic_component)

		if settings.per_day_basis == "Fixed 30 Days":
			days = 30
		else:
			days = date_diff(get_last_day(self.effective_date), get_first_day(self.effective_date)) + 1

		per_day_basic = flt(self.basic) / days
		self.per_day_basic = flt(per_day_basic, self.precision("per_day_basic"))
		self.amount = flt(per_day_basic * flt(self.no_of_days), self.precision("amount"))

	def create_additional_salary(self):
		component = frappe.db.get_single_value("Employee Warning Settings", "deduction_component")
		if not component:
			frappe.throw(_("Please set Deduction Salary Component in Employee Warning Settings"))

		additional_salary = frappe.get_doc(
			{
				"doctype": "Additional Salary",
				"employee": self.employee,
				"company": self.company,
				"salary_component": component,
				"type": "Deduction",
				"amount": self.amount,
				"currency": self.currency,
				"payroll_date": self.effective_date,
				"overwrite_salary_structure_amount": 0,
				"ref_doctype": self.doctype,
				"ref_docname": self.name,
			}
		)
		additional_salary.insert(ignore_permissions=True)
		additional_salary.submit()
		self.db_set("additional_salary", additional_salary.name)


def get_warning_level(number):
	number = cint(number)
	if 0 < number <= len(ORDINALS):
		return _("{0} Warning").format(_(ORDINALS[number - 1]))
	return _("Warning #{0}").format(number)


def get_basic_salary(employee, on_date, basic_component):
	"""Full-month (not prorated) amount of the basic salary component in the salary structure
	assigned to the employee on `on_date`."""
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
	from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
		get_assigned_salary_structure,
	)

	if not basic_component:
		frappe.throw(_("Please set Basic Salary Component in Employee Warning Settings"))

	structure = get_assigned_salary_structure(employee, on_date)
	if not structure:
		frappe.throw(_("No Salary Structure is assigned to Employee {0} on {1}").format(employee, on_date))

	row = frappe.db.get_value(
		"Salary Detail",
		{
			"parenttype": "Salary Structure",
			"parent": structure,
			"parentfield": "earnings",
			"salary_component": basic_component,
		},
		["amount", "amount_based_on_formula"],
		as_dict=True,
	)
	if not row:
		frappe.throw(
			_("Salary Component {0} is not in the earnings of Salary Structure {1}").format(
				frappe.bold(basic_component), frappe.bold(structure)
			)
		)

	if not row.amount_based_on_formula:
		return flt(row.amount)

	# formula based: evaluate the structure for the employee and take the unprorated amount
	slip = make_salary_slip(structure, employee=employee, posting_date=on_date, for_preview=1)
	for d in slip.earnings:
		if d.salary_component == basic_component:
			return flt(d.default_amount or d.amount)

	frappe.throw(
		_("Could not calculate {0} for Employee {1} from Salary Structure {2}").format(
			basic_component, employee, structure
		)
	)


def get_warning_history(employee, exclude=None):
	"""Approved warnings issued to the employee during their current employment."""
	if not employee:
		return []

	filters = {"employee": employee, "docstatus": 1, "status": "Approved"}
	date_of_joining = frappe.db.get_value("Employee", employee, "date_of_joining")
	if date_of_joining:
		filters["effective_date"] = (">=", date_of_joining)
	if exclude:
		filters["name"] = ("!=", exclude)

	return frappe.get_all(
		"Employee Warning",
		filters=filters,
		fields=[
			"name",
			"warning_type",
			"effective_date",
			"issue_date",
			"action",
			"no_of_days",
			"amount",
			"warning_level",
			"reason",
		],
		order_by="effective_date asc, creation asc",
	)


@frappe.whitelist()
def get_employee_warning_summary(employee, exclude=None):
	frappe.has_permission("Employee Warning", "read", throw=True)
	history = get_warning_history(employee, exclude)
	return {
		"history": history,
		"next_number": len(history) + 1,
		"next_level": get_warning_level(len(history) + 1),
	}


@frappe.whitelist()
def get_deduction_details(employee, effective_date, no_of_days, company=None):
	"""Preview of the deduction amount for the form (same calculation as on save)."""
	frappe.has_permission("Employee Warning", "read", throw=True)
	doc = frappe.new_doc("Employee Warning")
	doc.update(
		{
			"employee": employee,
			"effective_date": effective_date,
			"no_of_days": flt(no_of_days),
			"company": company or frappe.db.get_value("Employee", employee, "company"),
		}
	)
	doc.calculate_deduction()
	return {"basic": doc.basic, "per_day_basic": doc.per_day_basic, "amount": doc.amount}
