# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""End of Service (gratuity) statement of an employee up to a Till Date.

- Only Expats (Employee Category, from Nationality) with more than 1 year of service are eligible.
- Joined after 31-Jul-2023: (days in service / 365) * basic.
- Joined on or before 31-Jul-2023: the first 3 years (1095 days) on half basic, the rest on full:
  (days in first 3 years / 365) * basic / 2 + (remaining days / 365) * basic.
- Basic: the Freeze Basic for service up to its Till Date, the current basic for the days after.
"""

import frappe
from dateutil.relativedelta import relativedelta
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, flt, getdate

from hr_custom.hr_custom.doctype.employee_freeze_basic.employee_freeze_basic import get_freeze_basic
from hr_custom.utils import get_employee_category, get_nationality_field

# employees who joined on or before this date get half basic for their first 3 years
HALF_BASIC_JOINED_UPTO = getdate("2023-07-31")
HALF_BASIC_DAYS = 3 * 365
DAYS_IN_YEAR = 365
MIN_SERVICE_DAYS = 365


class EOSStatement(Document):
	def validate(self):
		self.set_employee_details()
		self.calculate()

	def set_employee_details(self):
		emp = frappe.get_doc("Employee", self.employee)
		if not emp.date_of_joining:
			frappe.throw(_("Date of Joining is not set for Employee {0}").format(self.employee))
		if getdate(self.till_date) < getdate(emp.date_of_joining):
			frappe.throw(_("Till Date cannot be before the Date of Joining"))

		nationality_field = get_nationality_field()
		self.update(
			{
				"employee_name": emp.employee_name,
				"department": emp.department,
				"designation": emp.designation,
				"date_of_joining": emp.date_of_joining,
				"company": emp.company,
				"currency": frappe.get_cached_value("Company", emp.company, "default_currency"),
				"nationality": emp.get(nationality_field) if nationality_field else None,
			}
		)
		self.employee_category = emp.get("employee_category") or get_employee_category(self.nationality)

	def calculate(self):
		doj, till = getdate(self.date_of_joining), getdate(self.till_date)
		self.service_days = date_diff(till, doj) + 1
		period = relativedelta(add_days(till, 1), doj)
		self.service_period = _("{0} Years {1} Months {2} Days").format(period.years, period.months, period.days)

		reasons = get_ineligibility_reasons(self.employee_category, self.service_days)
		self.eligible = int(not reasons)
		self.eligibility_remarks = " ".join(reasons) if reasons else _("Eligible")
		self.gratuity_details = []
		self.total_gratuity = 0
		if not self.eligible:
			return

		result = calculate_gratuity(self.employee, doj, till)
		self.update({k: v for k, v in result.items() if k != "details"})
		self.set("gratuity_details", result["details"])
		self.total_gratuity = flt(sum(flt(d.amount) for d in self.gratuity_details), 3)


def get_ineligibility_reasons(employee_category, service_days):
	reasons = []
	if employee_category != "Expat":
		reasons.append(
			_("Nationality is not set on the Employee, so the employee is not known to be an Expat.")
			if not employee_category
			else _("Gratuity is applicable only for Expats (employee is {0}).").format(_(employee_category))
		)
	if service_days <= MIN_SERVICE_DAYS:
		reasons.append(_("Service of {0} days is not more than 1 year.").format(service_days))
	return reasons


def calculate_gratuity(employee, date_of_joining, till_date, current_basic=None):
	"""Gratuity split into periods with the same basic and rate."""
	doj, till = getdate(date_of_joining), getdate(till_date)
	if current_basic is None:
		current_basic = get_current_basic(employee, till)
	freeze = get_freeze_basic(employee)

	half_basic = doj <= HALF_BASIC_JOINED_UPTO
	half_end = add_days(doj, HALF_BASIC_DAYS - 1) if half_basic else None
	freeze_end = getdate(freeze.till_date) if freeze else None

	# split the service at the end of the half-basic years and the end of the freeze basic
	cuts = sorted({d for d in (half_end, freeze_end) if d and doj <= d < till})
	details, start = [], doj
	for end in [*cuts, till]:
		on_freeze = bool(freeze_end and end <= freeze_end)
		basic = flt(freeze.freeze_basic) if on_freeze else current_basic
		is_half = bool(half_end and end <= half_end)
		days = date_diff(end, start) + 1
		details.append(
			{
				"from_date": start,
				"to_date": end,
				"days": days,
				"basic_type": _("Freeze") if on_freeze else _("Current"),
				"basic": basic,
				"rate": _("Half") if is_half else _("Full"),
				"amount": flt(days / DAYS_IN_YEAR * basic * (0.5 if is_half else 1), 3),
			}
		)
		start = add_days(end, 1)

	basis = (
		_("Joined on or before 31-Jul-2023: first 3 years on half basic, remaining years on full basic.")
		if half_basic
		else _("Joined after 31-Jul-2023: one month basic per year of service.")
	)
	if freeze:
		basis += " " + _("Freeze Basic {0} used up to {1}, current basic after that.").format(
			frappe.utils.fmt_money(freeze.freeze_basic), frappe.format(freeze.till_date, "Date")
		)

	return {
		"current_basic": current_basic,
		"freeze_basic_record": freeze.name if freeze else None,
		"freeze_basic": flt(freeze.freeze_basic) if freeze else 0,
		"freeze_till_date": freeze.till_date if freeze else None,
		"calculation_basis": basis,
		"details": details,
	}


def get_current_basic(employee, on_date):
	"""Full-month basic from the salary structure assigned on `on_date` (Basic Salary Component of
	Employee Warning Settings, else the earning named like 'Basic')."""
	from hr_custom.hr_custom.doctype.employee_warning.employee_warning import get_basic_salary

	component = frappe.db.get_single_value("Employee Warning Settings", "basic_component")
	if not component:
		component = frappe.db.get_value(
			"Salary Component", {"type": "Earning", "salary_component": ("like", "%basic%")}, "name"
		)
	return get_basic_salary(employee, on_date, component)
