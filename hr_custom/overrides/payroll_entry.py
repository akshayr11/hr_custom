import frappe
from frappe import _

from hr_custom.utils import get_employee_payroll_details, get_matching_employees


class PayrollEntryMixin:
	"""Adds Employee Category, Job Category and Payroll Cost Center filters to Payroll Entry."""

	def validate(self):
		super().validate()
		self.validate_employee_filters()
		self.set_employee_payroll_details()

	def has_employee_filters(self):
		return (
			self.get("employee_category") not in (None, "", "All")
			or bool(self.get("job_category"))
			or bool(self.get("payroll_cost_center"))
		)

	def get_allowed_employees(self):
		return get_matching_employees(
			[d.employee for d in self.employees],
			employee_category=self.get("employee_category"),
			payroll_cost_center=self.get("payroll_cost_center"),
			job_category=self.get("job_category"),
		)

	def get_filter_description(self):
		return _("Employee Category: {0}, Job Category: {1}, Payroll Cost Center: {2}").format(
			frappe.bold(self.get("employee_category") or _("All")),
			frappe.bold(self.get("job_category") or _("All")),
			frappe.bold(self.get("payroll_cost_center") or _("All")),
		)

	@frappe.whitelist()
	def fill_employee_details(self):
		result = super().fill_employee_details()
		if not self.has_employee_filters():
			self.set_employee_payroll_details()
			return result

		allowed = self.get_allowed_employees()
		self.set("employees", [d for d in self.employees if d.employee in allowed])
		self.number_of_employees = len(self.employees)

		if not self.employees:
			frappe.throw(
				_("No employees found for {0}").format(self.get_filter_description()),
				title=_("No employees found"),
			)

		self.set_employee_payroll_details()
		return self.get_employees_with_unmarked_attendance()

	def set_employee_payroll_details(self):
		"""Show each employee's category, job category and payroll cost center in Employee Details."""
		details = get_employee_payroll_details([d.employee for d in self.employees])
		fields = [
			f
			for f in ("employee_category", "job_category", "payroll_cost_center")
			if self.employees and self.employees[0].meta.has_field(f)
		]
		for row in self.employees:
			d = details.get(row.employee) or {}
			for f in fields:
				row.set(f, d.get(f))

	def validate_employee_filters(self):
		"""Catch rows added manually that don't match the filters."""
		if not self.has_employee_filters() or not self.employees:
			return

		allowed = self.get_allowed_employees()
		for row in self.employees:
			if row.employee not in allowed:
				frappe.throw(
					_("Row {0}: Employee {1} does not match {2}").format(
						row.idx, frappe.bold(row.employee), self.get_filter_description()
					)
				)
