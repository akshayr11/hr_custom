import frappe
from frappe import _
from frappe.utils import flt

from hr_custom.utils import get_employee_payroll_details, get_matching_employees

JE_AMOUNT_FIELDS = ("debit_in_account_currency", "credit_in_account_currency", "debit", "credit")


class PayrollEntryMixin:
	"""Adds Employee Category, Job Category and Payroll Cost Center filters to Payroll Entry, and
	posts the Payroll Payable (and, in the bank entry, the Bank) amounts by the employees' payroll
	cost centers instead of the Payroll Entry's one cost center."""

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

	def make_journal_entry(self, accounts, *args, **kwargs):
		"""HRMS splits the salary expense lines by the employees' payroll cost centers, but books the
		Payroll Payable line of the accrual and bank entries (and the Bank line) on the Payroll Entry's
		cost center. Split those by the same cost centers, in proportion to the employees' net pay
		(gross - deductions), so every cost center carries its own salaries."""
		voucher_type = kwargs.get("voucher_type") or "Journal Entry"
		accounts = self.distribute_by_payroll_cost_center(accounts, voucher_type)
		return super().make_journal_entry(accounts, *args, **kwargs)

	def distribute_by_payroll_cost_center(self, accounts, voucher_type):
		shares = self.get_cost_center_shares()
		if not shares:
			return accounts

		rows = []
		for row in accounts:
			is_payable = row.get("account") == self.payroll_payable_account and row.get("reference_name") == self.name
			is_bank = voucher_type == "Bank Entry" and row.get("account") == self.payment_account
			if not (is_payable or is_bank) or row.get("cost_center") != self.cost_center:
				rows.append(row)  # other lines, or already split by HRMS (employee-wise bank entry)
			elif row.get("party_type") == "Employee" and row.get("party"):
				rows += split_row(row, self.get_employee_shares(row["party"]))
			else:
				rows += split_row(row, shares)
		return rows

	def get_cost_center_shares(self):
		"""{cost center: share of the net pay} of the submitted salary slips."""
		if not hasattr(self, "_cost_center_shares"):
			totals = {}
			for slip in frappe.get_all(
				"Salary Slip",
				filters={"payroll_entry": self.name, "docstatus": 1},
				fields=["employee", "salary_structure", "base_gross_pay", "base_total_deduction"],
			):
				net = flt(slip.base_gross_pay) - flt(slip.base_total_deduction)
				for cost_center, share in self.get_employee_shares(slip.employee, slip.salary_structure).items():
					totals[cost_center] = totals.get(cost_center, 0) + net * share
			total = sum(v for v in totals.values() if v > 0)
			self._cost_center_shares = {cc: v / total for cc, v in totals.items() if v > 0} if total else {}
		return self._cost_center_shares

	def get_employee_shares(self, employee, salary_structure=None):
		"""{cost center: share} of the employee: the Salary Structure Assignment's Payroll Cost
		Centers, else the employee's / department's payroll cost center (HRMS's own rule)."""
		if not salary_structure:
			salary_structure = frappe.db.get_value(
				"Salary Slip", {"payroll_entry": self.name, "employee": employee, "docstatus": 1}, "salary_structure"
			)
		cost_centers = self.get_payroll_cost_centers_for_employee(employee, salary_structure)
		total = sum(flt(p) for p in cost_centers.values())
		return {cc: flt(p) / total for cc, p in cost_centers.items() if cc} if total else {}


def split_row(row, shares):
	"""The journal entry line split by {cost center: share}; the last line takes the rounding."""
	if len(shares) == 1 and next(iter(shares)) == row.get("cost_center"):
		return [row]

	precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")
	fields = [f for f in JE_AMOUNT_FIELDS if flt(row.get(f))]
	rows, allocated = [], dict.fromkeys(fields, 0.0)
	items = list(shares.items())
	for i, (cost_center, share) in enumerate(items):
		new = {**row, "cost_center": cost_center}
		for f in fields:
			if i == len(items) - 1:
				new[f] = flt(flt(row[f]) - allocated[f], precision)
			else:
				new[f] = flt(flt(row[f]) * share, precision)
				allocated[f] += new[f]
		if any(flt(new[f]) for f in fields):
			rows.append(new)
	return rows


def get_dashboard_data(data):
	"""Hide Overtime Slip from the Payroll Entry connections (overtime is paid through the salary slip)."""
	for group in data.get("transactions") or []:
		group["items"] = [d for d in group.get("items", []) if d != "Overtime Slip"]
	data["transactions"] = [g for g in data.get("transactions") or [] if g.get("items")]
	return data
