import frappe
from frappe import _

from hr_custom.utils import get_matching_employees


class PayrollEntryMixin:
	"""Adds Employee Category and Payroll Cost Center filters to Payroll Entry."""

	def validate(self):
		super().validate()
		self.validate_employee_filters()

	def has_employee_filters(self):
		return self.get("employee_category") not in (None, "", "All") or bool(self.get("payroll_cost_center"))

	@frappe.whitelist()
	def fill_employee_details(self):
		result = super().fill_employee_details()
		if not self.has_employee_filters():
			return result

		allowed = get_matching_employees(
			[d.employee for d in self.employees], self.employee_category, self.payroll_cost_center
		)
		self.set("employees", [d for d in self.employees if d.employee in allowed])
		self.number_of_employees = len(self.employees)

		if not self.employees:
			frappe.throw(
				_("No employees found for Employee Category {0} and Payroll Cost Center {1}").format(
					frappe.bold(self.employee_category or _("All")),
					frappe.bold(self.payroll_cost_center or _("All")),
				),
				title=_("No employees found"),
			)

		return self.get_employees_with_unmarked_attendance()

	def validate_employee_filters(self):
		"""Catch rows added manually that don't match the filters."""
		if not self.has_employee_filters() or not self.employees:
			return

		allowed = get_matching_employees(
			[d.employee for d in self.employees], self.employee_category, self.payroll_cost_center
		)
		for row in self.employees:
			if row.employee not in allowed:
				frappe.throw(
					_("Row {0}: Employee {1} does not match Employee Category {2} / Payroll Cost Center {3}").format(
						row.idx,
						frappe.bold(row.employee),
						self.employee_category or _("All"),
						self.payroll_cost_center or _("All"),
					)
				)
