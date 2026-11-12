# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Attendance Deduction: the deduction minutes of the period's attendance (late entry, early
exit, no check-out - see hr_custom.overrides.attendance) per employee, for approval.

The approver can change an employee's Approved Minutes with a justification.
Deduction Amount = Total Salary x Approved Minutes / Deduction Divisor (14400 by default),
Total Salary being the full month earnings of the employee's salary structure.
Approving (workflow -> submit) creates an Additional Salary of the deduction component per
employee, which the Payroll Entry of the Payroll Date picks up; cancelling cancels them.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_link_to_form, getdate

from hr_custom.utils import get_employee_payroll_details, get_matching_employees

# 30 days x 8 hours x 60 minutes
DEFAULT_DIVISOR = 14400


class AttendanceDeduction(Document):
	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date"))
		if frappe.db.get_value("Salary Component", self.salary_component, "type") != "Deduction":
			frappe.throw(_("{0} is not a Deduction component").format(frappe.bold(self.salary_component)))
		self.validate_duplicate_employees()
		self.calculate()

	def validate_duplicate_employees(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(_("Row {0}: Employee {1} is added twice").format(row.idx, row.employee))
			seen.add(row.employee)

		other = get_deducted_employees(self.from_date, self.to_date, exclude=self.name)
		for row in self.employees:
			if row.employee in other:
				frappe.throw(
					_("Row {0}: {1} is already in {2} for this period").format(
						row.idx, row.employee, get_link_to_form("Attendance Deduction", other[row.employee])
					)
				)

	def calculate(self):
		if not flt(self.deduction_divisor):
			self.deduction_divisor = DEFAULT_DIVISOR
		divisor = flt(self.deduction_divisor)

		for row in self.employees:
			if row.approved_minutes is None:
				row.approved_minutes = row.deduction_minutes
			if row.approved_minutes != row.deduction_minutes and not (row.justification or "").strip():
				frappe.throw(
					_("Row {0}: Justification is required as the Approved Minutes of {1} are changed").format(
						row.idx, frappe.bold(row.employee_name or row.employee)
					)
				)
			row.deduction_amount = flt(flt(row.total_salary) * row.approved_minutes / divisor, 3)

		self.total_employees = len(self.employees)
		self.total_deduction_minutes = sum(row.deduction_minutes or 0 for row in self.employees)
		self.total_approved_minutes = sum(row.approved_minutes or 0 for row in self.employees)
		self.total_deduction_amount = sum(flt(row.deduction_amount) for row in self.employees)

	@frappe.whitelist()
	def get_employees(self):
		"""Fill the employees and day-wise details from the submitted attendance of the period."""
		self.set("employees", [])
		self.set("details", [])

		attendance = get_attendance(self.company, self.from_date, self.to_date)
		employees = {d.employee for d in attendance}
		if self.payroll_cost_center:
			employees = get_matching_employees(employees, payroll_cost_center=self.payroll_cost_center)
		already = get_deducted_employees(self.from_date, self.to_date, exclude=self.name)
		skipped = sorted(employees & set(already))
		employees -= set(already)

		cost_centers = get_employee_payroll_details(list(employees))
		rows = {}
		for d in attendance:
			if d.employee not in employees:
				continue
			row = rows.get(d.employee)
			if not row:
				row = rows[d.employee] = frappe._dict(
					employee=d.employee,
					employee_name=d.employee_name,
					payroll_cost_center=(cost_centers.get(d.employee) or {}).get("payroll_cost_center"),
					days=0,
					deduction_minutes=0,
					extra_minutes=0,
				)
			row.extra_minutes += d.extra_minutes or 0
			if not d.deduction_minutes:
				continue
			row.days += 1
			row.deduction_minutes += d.deduction_minutes
			self.append(
				"details",
				{
					"employee": d.employee,
					"attendance_date": d.attendance_date,
					"attendance": d.name,
					"shift": d.shift,
					"in_time": d.in_time,
					"out_time": d.out_time,
					"in_diff_minutes": d.in_diff_minutes,
					"out_diff_minutes": d.out_diff_minutes,
					"missing_out": 1 if d.in_time and (not d.out_time or d.out_time == d.in_time) else 0,
					"worked_minutes": d.worked_minutes,
					"extra_minutes": d.extra_minutes,
					"deduction_minutes": d.deduction_minutes,
				},
			)

		for row in sorted(rows.values(), key=lambda r: r.employee):
			if not row.deduction_minutes:
				continue
			row.total_salary = get_total_salary(row.employee, self.to_date)
			row.approved_minutes = row.deduction_minutes
			self.append("employees", row)

		if skipped:
			frappe.msgprint(
				_("Already in another Attendance Deduction for this period: {0}").format(", ".join(skipped)),
				indicator="orange",
			)
		self.calculate()

	def on_submit(self):
		for row in self.employees:
			if flt(row.deduction_amount) <= 0:
				continue
			additional_salary = frappe.get_doc(
				{
					"doctype": "Additional Salary",
					"employee": row.employee,
					"company": self.company,
					"salary_component": self.salary_component,
					"amount": row.deduction_amount,
					"payroll_date": self.payroll_date,
					"overwrite_salary_structure_amount": 0,
					"ref_doctype": self.doctype,
					"ref_docname": self.name,
				}
			)
			additional_salary.flags.ignore_permissions = True
			additional_salary.insert()
			additional_salary.submit()
			row.db_set("additional_salary", additional_salary.name)

	def on_cancel(self):
		for row in self.employees:
			if row.additional_salary and frappe.db.get_value("Additional Salary", row.additional_salary, "docstatus") == 1:
				additional_salary = frappe.get_doc("Additional Salary", row.additional_salary)
				additional_salary.flags.ignore_permissions = True
				additional_salary.cancel()


def get_attendance(company, from_date, to_date):
	return frappe.get_all(
		"Attendance",
		filters={
			"company": company,
			"docstatus": 1,
			"attendance_date": ("between", [from_date, to_date]),
		},
		or_filters={"deduction_minutes": (">", 0), "extra_minutes": (">", 0)},
		fields=[
			"name",
			"employee",
			"employee_name",
			"attendance_date",
			"shift",
			"in_time",
			"out_time",
			"in_diff_minutes",
			"out_diff_minutes",
			"worked_minutes",
			"extra_minutes",
			"deduction_minutes",
		],
		order_by="employee, attendance_date",
	)


def get_deducted_employees(from_date, to_date, exclude=None):
	"""{employee: Attendance Deduction} of the not cancelled deductions overlapping the period."""
	parent = frappe.qb.DocType("Attendance Deduction")
	child = frappe.qb.DocType("Attendance Deduction Employee")
	query = (
		frappe.qb.from_(child)
		.join(parent)
		.on(child.parent == parent.name)
		.select(child.employee, parent.name)
		.where(
			(parent.docstatus < 2)
			& (parent.from_date <= to_date)
			& (parent.to_date >= from_date)
			& (child.parenttype == "Attendance Deduction")
		)
	)
	if exclude:
		query = query.where(parent.name != exclude)
	return dict(query.run())


def get_total_salary(employee, on_date):
	"""Full month earnings of the salary structure assigned on `on_date` (0 when none)."""
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
	from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
		get_assigned_salary_structure,
	)

	structure = get_assigned_salary_structure(employee, on_date)
	if not structure:
		frappe.msgprint(_("No Salary Structure is assigned to {0}: Total Salary is 0").format(employee), indicator="orange")
		return 0

	try:
		slip = make_salary_slip(structure, employee=employee, posting_date=on_date, for_preview=1)
	except Exception:
		frappe.clear_messages()
		frappe.msgprint(_("Could not calculate the salary of {0}: Total Salary is 0").format(employee), indicator="orange")
		return 0

	total = flt(
		sum(
			flt(d.default_amount or d.amount)
			for d in slip.earnings
			if not (d.statistical_component or d.do_not_include_in_total or d.additional_salary)
		),
		3,
	)
	if not total:
		frappe.msgprint(_("Salary Structure {0} of {1} has no earnings: Total Salary is 0").format(structure, employee), indicator="orange")
	return total
