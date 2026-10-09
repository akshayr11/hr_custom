# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt, get_last_day, getdate

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
		self.validate_duplicate_employees()
		self.validate_already_included()
		self.set_totals()

	def on_submit(self):
		if not self.employees:
			frappe.throw(_("Add at least one employee before submitting"))

	def get_month_number(self):
		return MONTHS.index(self.month) + 1

	def get_period(self):
		start = getdate(f"{self.year}-{self.get_month_number():02d}-01")
		return start, get_last_day(start)

	def set_head_office_selected(self):
		head_office = set(get_head_office_cost_centers())
		self.head_office_selected = int(any(d.cost_center in head_office for d in self.cost_centers))
		if self.based_on == "Cost Center" and not self.head_office_selected:
			self.departments = []

	def validate_duplicate_employees(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(_("Row {0}: Employee {1} is added more than once").format(row.idx, row.employee))
			seen.add(row.employee)

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
		self.total_employees = len(self.employees)
		self.total_ot_amount = sum(flt(d.ot_amount) for d in self.employees)
		self.total_amount = sum(flt(d.amount) for d in self.employees)

	@frappe.whitelist()
	def get_employees(self):
		for field in ("company", "month", "year", "bank", "ot_type"):
			if not self.get(field):
				frappe.throw(_("Please set {0}").format(self.meta.get_label(field)))

		self.set_head_office_selected()
		self.employees = []

		included = get_included_employees(self.company, self.month, self.year, self.ot_type, self.name)
		slips = [d for d in self.get_salary_slips() if d.employee not in included]
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

		for row in rows.values():
			if self.ot_type == "With OT":
				row.amount = row.net_pay
			elif self.ot_type == "Without OT":
				row.amount = row.net_pay - row.ot_amount
			else:
				row.amount = row.ot_amount

			if flt(row.amount) > 0:
				self.append("employees", row)

		self.set_totals()
		return len(self.employees)

	def get_salary_slips(self):
		start, end = self.get_period()
		ss = frappe.qb.DocType("Salary Slip")
		emp = frappe.qb.DocType("Employee")

		query = (
			frappe.qb.from_(ss)
			.join(emp)
			.on(ss.employee == emp.name)
			.select(
				ss.name.as_("salary_slip"),
				ss.employee,
				ss.employee_name,
				ss.gross_pay,
				ss.net_pay,
				ss.payment_days,
				emp.payroll_cost_center.as_("cost_center"),
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
				& (emp.bank_name == self.bank)
			)
			.orderby(ss.employee_name)
		)

		if self.emp_category:
			query = query.where(emp.employment_type == self.emp_category)

		if self.based_on == "Employee":
			employees = [d.employee for d in self.selected_employees]
			if not employees:
				frappe.throw(_("Please select Employees"))
			query = query.where(ss.employee.isin(employees))

		elif self.based_on == "Department":
			departments = expand_tree("Department", [d.department for d in self.departments])
			if not departments:
				frappe.throw(_("Please select Departments"))
			query = query.where(emp.department.isin(departments))

		slips = query.run(as_dict=True)

		if self.based_on == "Cost Center":
			slips = self.filter_by_cost_center(slips)

		return slips

	def filter_by_cost_center(self, slips):
		if not self.cost_centers:
			frappe.throw(_("Please select Cost Centers"))

		head_office = set(get_head_office_cost_centers())
		selected = {d.cost_center for d in self.cost_centers}
		head_office_ccs = set(expand_tree("Cost Center", selected & head_office))
		other_ccs = set(expand_tree("Cost Center", selected - head_office))
		departments = set(expand_tree("Department", [d.department for d in self.departments]))

		def include(slip):
			if slip.cost_center in other_ccs:
				return True
			if slip.cost_center in head_office_ccs:
				return not departments or slip.department in departments
			return False

		return [d for d in slips if include(d)]


def expand_tree(doctype, names):
	"""Return the given nodes along with all their descendants."""
	result = set()
	for name in names:
		if not name:
			continue
		result.add(name)
		result.update(frappe.db.get_descendants(doctype, name) or [])
	return list(result)


def get_head_office_cost_centers():
	return frappe.get_all("Cost Center", filters={"is_head_office": 1}, pluck="name")


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
