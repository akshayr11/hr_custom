# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.query_builder.functions import Coalesce, NullIf
from frappe.utils import flt, get_last_day, getdate

from hr_custom.hr_custom.doctype.ohb_bank_loan.ohb_bank_loan import (
	LOAN_ENTRY,
	SALARY_ENTRY,
	get_loan_installments,
	update_paid_amounts,
)
from hr_custom.utils import EMPLOYEE_CATEGORIES, employee_payroll_cost_center, has_employee_category

MONTHS = [
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
]

# Which part of the salary each letter type pays. Two letters for the same employee and
# month conflict only when they pay an overlapping part, so "Without OT" and "OT Only"
# letters can coexist, but "With OT" blocks both.
OT_TYPE_PARTS = {
	"With OT": {"salary", "ot"},
	"Without OT": {"salary"},
	"OT Only": {"ot"},
}


class BankLetter(Document):
	def autoname(self):
		# BNKLTR/<MM>/<YYYY>/0001 - counter restarts for every payroll month
		self.name = make_autoname(f"BNKLTR/{self.get_month_number():02d}/{self.year}/.####", doc=self)

	def validate(self):
		self.set_head_office_selected()
		self.validate_head_office_departments()
		self.validate_duplicate_employees()
		self.validate_already_included()
		self.set_totals()

	def on_submit(self):
		if not self.employees:
			frappe.throw(_("Add at least one employee before submitting"))
		self.update_loans()

	def on_cancel(self):
		self.update_loans()

	def update_loans(self):
		update_paid_amounts([d.ohb_bank_loan for d in self.employees if d.entry_type == LOAN_ENTRY])

	def get_month_number(self):
		return MONTHS.index(self.month) + 1

	def get_period(self):
		start = getdate(f"{self.year}-{self.get_month_number():02d}-01")
		return start, get_last_day(start)

	def set_head_office_selected(self):
		if self.get("all_cost_centers"):
			self.cost_centers = []
		if self.get("all_departments"):
			self.departments = []

		head_office = set(get_head_office_cost_centers(self.company))
		if self.based_on == "Cost Center" and self.get("all_cost_centers"):
			self.head_office_selected = int(bool(head_office))
		else:
			self.head_office_selected = int(any(d.cost_center in head_office for d in self.cost_centers))

		if self.based_on == "Cost Center" and not self.head_office_selected:
			self.departments = []
			self.all_departments = 0

	def validate_head_office_departments(self):
		if (
			self.based_on == "Cost Center"
			and self.head_office_selected
			and not self.departments
			and not self.get("all_departments")
		):
			frappe.throw(
				_("Please select Departments for the Head Office cost center, or tick All Departments")
			)

	def validate_duplicate_employees(self):
		# an employee with an OHB loan has two rows: salary and loan installment
		seen = set()
		for row in self.employees:
			key = (row.employee, row.entry_type or SALARY_ENTRY)
			if key in seen:
				frappe.throw(_("Row {0}: Employee {1} is added more than once").format(row.idx, row.employee))
			seen.add(key)

	def validate_already_included(self):
		included = get_included_employees(self.company, self.month, self.year, self.ot_type, self.name)
		for row in self.employees:
			if row.employee in included:
				letter, ot_type = included[row.employee]
				frappe.throw(
					_("Row {0}: Employee {1} is already included in Bank Letter {2} ({3}) for {4} {5}").format(
						row.idx, row.employee, letter, ot_type, self.month, self.year
					)
				)

	def set_totals(self):
		self.total_employees = len({d.employee for d in self.employees})
		self.total_ot_amount = sum(flt(d.ot_amount) for d in self.employees)
		self.total_amount = sum(flt(d.amount) for d in self.employees)

	@frappe.whitelist()
	def get_employees(self):
		for field in ("company", "month", "year", "bank", "ot_type"):
			if not self.get(field):
				frappe.throw(_("Please set {0}").format(self.meta.get_label(field)))

		self.set_head_office_selected()
		self.validate_head_office_departments()
		self.employees = []

		slips, reason = self.get_filtered_salary_slips()
		ot_amounts = get_ot_amounts([d.salary_slip for d in slips])

		rows = {}
		for slip in slips:
			ot_amount = flt(ot_amounts.get(slip.salary_slip))
			row = rows.setdefault(
				slip.employee,
				frappe._dict(
					employee=slip.employee,
					employee_name=slip.employee_name,
					cost_center=slip.cost_center,
					department=slip.department,
					bank_name=slip.bank_name,
					bank_ac_no=slip.bank_ac_no,
					iban=slip.iban,
					gross_pay=0,
					ot_amount=0,
					net_pay=0,
					payment_days=0,
				),
			)
			# an employee can have more than one slip in a month (e.g. off-cycle payroll)
			row.salary_slip = slip.salary_slip
			row.gross_pay += flt(slip.gross_pay)
			row.net_pay += flt(slip.net_pay)
			row.ot_amount += ot_amount
			row.payment_days += flt(slip.payment_days)

		# OHB loan installments come out of the salary, never out of an OT-only transfer
		loans = {}
		if self.ot_type != "OT Only":
			loans = get_loan_installments(self.company, rows, self.get_period()[1])

		for row in rows.values():
			if self.ot_type == "With OT":
				row.amount = row.net_pay
			elif self.ot_type == "Without OT":
				row.amount = row.net_pay - row.ot_amount
			else:
				row.amount = row.ot_amount

			if flt(row.amount) <= 0:
				continue

			row.entry_type = SALARY_ENTRY
			loan = loans.get(row.employee)
			installment = min(flt(loan.installment), flt(row.amount)) if loan else 0
			row.amount = flt(row.amount) - installment
			if row.amount > 0:
				self.append("employees", row)

			if installment > 0:
				self.append(
					"employees",
					{
						"employee": row.employee,
						"employee_name": row.employee_name,
						"cost_center": row.cost_center,
						"department": row.department,
						"entry_type": LOAN_ENTRY,
						"ohb_bank_loan": loan.name,
						"bank_name": loan.bank,
						"bank_ac_no": loan.ohb_account_no,
						"salary_slip": row.salary_slip,
						"amount": installment,
						"loan_balance": flt(loan.balance) - installment,
					},
				)

		if rows and not self.employees:
			reason = _("{0} employee(s) matched, but their amount to transfer is 0 for {1}.").format(
				len(rows), frappe.bold(_(self.ot_type))
			)
			if self.ot_type == "OT Only":
				reason += " " + _(
					"No OT earnings found. Mark OT salary components with 'Is Overtime (OT) Component'."
				)

		self.set_totals()
		return {"count": len(self.employees), "reason": reason}

	def get_filtered_salary_slips(self):
		"""Apply the letter's filters one by one. Returns (slips, reason) where reason explains which
		filter left no employees."""
		slips = self.get_salary_slips()
		if not slips:
			return [], _(
				"No submitted Salary Slips found for {0} with start date in {1} {2}. Submit the Payroll Entry's salary slips first."
			).format(frappe.bold(self.company), frappe.bold(_(self.month)), self.year)

		filters = [
			(
				lambda d: normalize(d.bank_name) == normalize(self.bank),
				lambda found: _("None of them have Bank Name {0} on the Employee master.").format(
					frappe.bold(self.bank)
				)
				+ summarize(_("Bank Name on these employees"), found, "bank_name"),
			)
		]

		if self.emp_category in EMPLOYEE_CATEGORIES:
			if not has_employee_category():
				frappe.throw(_("Employee Category field is missing on Employee. Please run bench migrate."))
			filters.append(
				(
					lambda d: d.employee_category == self.emp_category,
					lambda found: _("None of them have Employee Category {0} (set from Nationality).").format(
						frappe.bold(self.emp_category)
					)
					+ summarize(_("Employee Category"), found, "employee_category"),
				)
			)

		filters.append(self.get_selection_filter())

		included = get_included_employees(self.company, self.month, self.year, self.ot_type, self.name)
		filters.append(
			(
				lambda d: d.employee not in included,
				lambda found: _("All of them are already included in another Bank Letter for {0} {1}: {2}").format(
					_(self.month), self.year, ", ".join(sorted({included[d.employee][0] for d in found}))
				),
			)
		)

		total = len({d.employee for d in slips})
		for keep, explain in filters:
			remaining = [d for d in slips if keep(d)]
			if not remaining:
				intro = _("{0} employee(s) have submitted Salary Slips for {1} {2}.").format(
					total, _(self.month), self.year
				)
				checked = len({d.employee for d in slips})
				if checked < total:
					intro += " " + _("{0} of them passed the earlier filters.").format(checked)
				return [], intro + "<br><br>" + explain(slips)
			slips = remaining

		return slips, None

	def get_selection_filter(self):
		"""(keep, explain) for the Based On selection: Employee / Department / Cost Center."""
		if self.based_on == "Employee":
			employees = {d.employee for d in self.selected_employees}
			if not employees:
				frappe.throw(_("Please select Employees"))
			return (
				lambda d: d.employee in employees,
				lambda found: _("None of the selected employees have a submitted Salary Slip with this Bank."),
			)

		if self.based_on == "Department":
			if self.get("all_departments"):
				return (lambda d: True, lambda found: "")

			departments = set(expand_tree("Department", [d.department for d in self.departments]))
			if not departments:
				frappe.throw(_("Please select Departments or tick All Departments"))
			return (
				lambda d: d.department in departments,
				lambda found: _("None of them are in the selected Departments.")
				+ summarize(_("Departments of these employees"), found, "department"),
			)

		if not self.cost_centers and not self.get("all_cost_centers"):
			frappe.throw(_("Please select Cost Centers or tick All Cost Centers"))

		head_office = set(get_head_office_cost_centers(self.company))
		departments = set(expand_tree("Department", [d.department for d in self.departments]))

		def department_ok(slip):
			return self.get("all_departments") or not departments or slip.department in departments

		if self.get("all_cost_centers"):
			# everyone, including employees without a cost center; Head Office still by department
			head_office_ccs = set(expand_tree("Cost Center", head_office))

			def keep(slip):
				return department_ok(slip) if slip.cost_center in head_office_ccs else True

		else:
			selected = {d.cost_center for d in self.cost_centers}
			head_office_ccs = set(expand_tree("Cost Center", selected & head_office))
			other_ccs = set(expand_tree("Cost Center", selected - head_office))

			def keep(slip):
				if slip.cost_center in other_ccs:
					return True
				if slip.cost_center in head_office_ccs:
					return department_ok(slip)
				return False

		return (
			keep,
			lambda found: _(
				"None of them are in the selected Cost Centers. The cost center comes from the Payroll Entry's Payroll Cost Center, else the Employee's (or their Department's) Payroll Cost Center."
			)
			+ summarize(_("Payroll Cost Center of these employees"), found, "cost_center"),
		)

	def get_salary_slips(self):
		"""All submitted salary slips of the company for the month, with the employee details used
		by the filters."""
		start, end = self.get_period()
		ss = frappe.qb.DocType("Salary Slip")
		emp = frappe.qb.DocType("Employee")
		dept = frappe.qb.DocType("Department")
		pe = frappe.qb.DocType("Payroll Entry")

		query = (
			frappe.qb.from_(ss)
			.join(emp)
			.on(ss.employee == emp.name)
			.left_join(dept)
			.on(emp.department == dept.name)
			.left_join(pe)
			.on(ss.payroll_entry == pe.name)
			.select(
				ss.name.as_("salary_slip"),
				ss.employee,
				ss.employee_name,
				ss.gross_pay,
				ss.net_pay,
				ss.payment_days,
				# Payroll Cost Center of the month's Payroll Entry; when that entry was run for all
				# cost centers (or the slip has no entry), the employee's payroll cost center
				Coalesce(NullIf(pe.payroll_cost_center, ""), employee_payroll_cost_center(emp, dept)).as_(
					"cost_center"
				),
				emp.department,
				emp.bank_name,
				emp.bank_ac_no,
				emp.iban,
			)
			.where(
				(ss.docstatus == 1)
				& (ss.company == self.company)
				& (ss.start_date >= start)
				& (ss.start_date <= end)
			)
			.orderby(ss.employee_name)
		)
		if has_employee_category():
			query = query.select(emp.employee_category)

		return query.run(as_dict=True)


def normalize(value):
	return (value or "").strip().lower()


def summarize(label, slips, field, limit=8):
	"""'<br>Label: A (3), Not set (2)' for the values of `field` across the slips' employees."""
	from collections import Counter

	counts = Counter()
	seen = set()
	for d in slips:
		if d.employee in seen:
			continue
		seen.add(d.employee)
		counts[d.get(field) or _("Not set")] += 1

	values = ", ".join(
		f"{frappe.utils.escape_html(str(value))} ({count})" for value, count in counts.most_common(limit)
	)
	return f"<br>{label}: {values}"


def expand_tree(doctype, names):
	"""Return the given nodes along with all their descendants."""
	result = set()
	for name in names:
		if not name:
			continue
		result.add(name)
		result.update(frappe.db.get_descendants(doctype, name) or [])
	return list(result)


def get_head_office_cost_centers(company=None):
	filters = {"is_head_office": 1}
	if company:
		filters["company"] = company
	return frappe.get_all("Cost Center", filters=filters, pluck="name")


def get_ot_components():
	components = set(frappe.get_all("Salary Component", filters={"is_overtime_component": 1}, pluck="name"))
	if frappe.db.exists("DocType", "Overtime Type"):
		components.update(
			frappe.get_all(
				"Overtime Type",
				filters={"overtime_salary_component": ("is", "set")},
				pluck="overtime_salary_component",
			)
		)
	return list(components)


def get_ot_amounts(salary_slips):
	components = get_ot_components()
	if not salary_slips or not components:
		return {}

	sd = frappe.qb.DocType("Salary Detail")
	data = (
		frappe.qb.from_(sd)
		.select(sd.parent, frappe.query_builder.functions.Sum(sd.amount))
		.where(
			(sd.parenttype == "Salary Slip")
			& (sd.parentfield == "earnings")
			& (sd.parent.isin(salary_slips))
			& (sd.salary_component.isin(components))
		)
		.groupby(sd.parent)
		.run()
	)
	return dict(data)


def get_included_employees(company, month, year, ot_type, exclude_letter=None):
	"""Employees already in a draft/submitted letter of the same month whose pay part overlaps
	with `ot_type`. Returns {employee: (letter, letter_ot_type)}."""
	conflicting_types = [t for t, parts in OT_TYPE_PARTS.items() if parts & OT_TYPE_PARTS[ot_type]]

	bl = frappe.qb.DocType("Bank Letter")
	ble = frappe.qb.DocType("Bank Letter Employee")
	query = (
		frappe.qb.from_(ble)
		.join(bl)
		.on(ble.parent == bl.name)
		.select(ble.employee, bl.name, bl.ot_type)
		.where(
			(ble.parenttype == "Bank Letter")
			& (bl.docstatus < 2)
			& (bl.company == company)
			& (bl.month == month)
			& (bl.year == year)
			& (bl.ot_type.isin(conflicting_types))
		)
	)
	if exclude_letter:
		query = query.where(bl.name != exclude_letter)

	return {d[0]: (d[1], d[2]) for d in query.run()}


@frappe.whitelist()
def get_month_letters(company, month, year, exclude_letter=None):
	"""Bank letters already created for the month, so the user can see whether OT was paid."""
	filters = {"company": company, "month": month, "year": year, "docstatus": ("<", 2)}
	if exclude_letter:
		filters["name"] = ("!=", exclude_letter)

	return frappe.get_all(
		"Bank Letter",
		filters=filters,
		fields=["name", "ot_type", "docstatus", "bank", "total_employees", "total_amount"],
		order_by="creation",
	)
