# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""OHB (Oman Housing Bank) loan of an employee. While the loan is Approved (submitted) and Active,
every Bank Letter that pays the employee's salary splits it in two entries: the salary less the
monthly installment to the employee's own account, and the installment to the OHB account."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate, nowdate

from hr_custom.utils import EMPLOYEE_LOCATION_FIELD, employee_payroll_cost_center

LOAN_ENTRY = "OHB Loan"
SALARY_ENTRY = "Salary"


class OHBBankLoan(Document):
	def validate(self):
		if self.docstatus == 0:
			self.update(get_employee_details(self.employee))
		self.validate_amounts()
		self.validate_active_loan()
		self.set_balance()

	def before_update_after_submit(self):
		self.validate_active_loan()

	def validate_amounts(self):
		if flt(self.total_loan_amount) <= 0:
			frappe.throw(_("Total Loan Amount must be greater than 0"))
		if flt(self.monthly_installment) <= 0:
			frappe.throw(_("Monthly Installment must be greater than 0"))
		if flt(self.monthly_installment) > flt(self.total_loan_amount):
			frappe.throw(_("Monthly Installment cannot be more than the Total Loan Amount"))

	def validate_active_loan(self):
		"""One active loan per employee, so a Bank Letter knows which installment to deduct."""
		if self.status != "Active":
			return

		other = frappe.db.get_value(
			"OHB Bank Loan",
			{
				"employee": self.employee,
				"status": "Active",
				"docstatus": ("<", 2),
				"name": ("!=", self.name),
			},
		)
		if other:
			frappe.throw(
				_("Employee {0} already has an active OHB Bank Loan {1}. Set it to Inactive first.").format(
					frappe.bold(self.employee_name or self.employee), frappe.bold(other)
				)
			)

	def set_balance(self):
		self.paid_amount = get_paid_amounts([self.name]).get(self.name, 0) if not self.is_new() else 0
		self.balance_amount = flt(self.total_loan_amount) - flt(self.paid_amount)


@frappe.whitelist()
def get_employee_details(employee):
	"""Values shown in the loan's Employee section."""
	if not employee:
		return {}

	meta = frappe.get_meta("Employee")
	fields = ["employee_name", "company", "department", "designation", "date_of_joining", "employment_type"]
	optional = {
		"location": EMPLOYEE_LOCATION_FIELD if meta.has_field(EMPLOYEE_LOCATION_FIELD) else "branch",
		"job_category": "job_category" if meta.has_field("job_category") else None,
	}
	emp = frappe.db.get_value(
		"Employee", employee, fields + [f for f in optional.values() if f], as_dict=True
	)
	if not emp:
		return {}

	company_currency = frappe.get_cached_value("Company", emp.company, "default_currency")
	return {
		"employee_name": emp.employee_name,
		"company": emp.company,
		"currency": company_currency,
		"department": emp.department,
		"designation": emp.designation,
		"date_of_joining": emp.date_of_joining,
		"employee_type": emp.employment_type,
		"location": emp.get(optional["location"]),
		"job_category": emp.get(optional["job_category"]) if optional["job_category"] else None,
		"payroll_cost_center": get_payroll_cost_center(employee),
		"gross_salary": get_gross_salary(employee),
	}


def get_payroll_cost_center(employee):
	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	result = (
		frappe.qb.from_(emp)
		.left_join(dept)
		.on(emp.department == dept.name)
		.select(employee_payroll_cost_center(emp, dept))
		.where(emp.name == employee)
		.run()
	)
	return result[0][0] if result else None


def get_gross_salary(employee, on_date=None):
	"""Full-month gross of the salary structure assigned to the employee, else the gross of their
	latest submitted salary slip."""
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
	from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
		get_assigned_salary_structure,
	)

	on_date = on_date or nowdate()
	structure = get_assigned_salary_structure(employee, on_date)
	if structure:
		try:
			slip = make_salary_slip(structure, employee=employee, posting_date=on_date, for_preview=1)
			return flt(slip.gross_pay)
		except Exception:
			# e.g. missing holiday list / payroll settings; fall back to the last slip
			frappe.clear_messages()

	slip = frappe.get_all(
		"Salary Slip",
		filters={"employee": employee, "docstatus": 1},
		fields=["gross_pay"],
		order_by="start_date desc",
		limit=1,
	)
	return flt(slip[0].gross_pay) if slip else 0


def get_paid_amounts(loans):
	"""{loan: installments transferred through submitted Bank Letters}"""
	if not loans:
		return {}

	bl = frappe.qb.DocType("Bank Letter")
	ble = frappe.qb.DocType("Bank Letter Employee")
	data = (
		frappe.qb.from_(ble)
		.join(bl)
		.on(ble.parent == bl.name)
		.select(ble.ohb_bank_loan, Sum(ble.amount))
		.where(
			(ble.parenttype == "Bank Letter")
			& (bl.docstatus == 1)
			& (ble.entry_type == LOAN_ENTRY)
			& (ble.ohb_bank_loan.isin(loans))
		)
		.groupby(ble.ohb_bank_loan)
		.run()
	)
	return {loan: flt(amount) for loan, amount in data}


def update_paid_amounts(loans):
	"""Called when a Bank Letter is submitted / cancelled: rebuild each loan's repayment history,
	paid amount and balance from its submitted Bank Letters."""
	from hr_custom.hr_custom.doctype.bank_letter.bank_letter import MONTHS

	loans = list({d for d in loans if d})
	if not loans:
		return

	bl = frappe.qb.DocType("Bank Letter")
	ble = frappe.qb.DocType("Bank Letter Employee")
	payments = (
		frappe.qb.from_(ble)
		.join(bl)
		.on(ble.parent == bl.name)
		.select(ble.ohb_bank_loan, ble.amount, bl.name, bl.month, bl.year, bl.letter_date)
		.where(
			(ble.parenttype == "Bank Letter")
			& (bl.docstatus == 1)
			& (ble.entry_type == LOAN_ENTRY)
			& (ble.ohb_bank_loan.isin(loans))
		)
		.run(as_dict=True)
	)

	for loan in loans:
		total = flt(frappe.db.get_value("OHB Bank Loan", loan, "total_loan_amount"))
		rows = sorted(
			(d for d in payments if d.ohb_bank_loan == loan),
			key=lambda d: (d.year, MONTHS.index(d.month), getdate(d.letter_date), d.name),
		)

		# child rows are written directly: the loan is submitted and the Bank Letter's user may
		# not have edit rights on it
		frappe.db.delete("OHB Loan Repayment", {"parent": loan, "parenttype": "OHB Bank Loan"})
		balance = total
		for idx, d in enumerate(rows, 1):
			opening, balance = balance, balance - flt(d.amount)
			frappe.get_doc(
				{
					"doctype": "OHB Loan Repayment",
					"parent": loan,
					"parenttype": "OHB Bank Loan",
					"parentfield": "repayments",
					"idx": idx,
					"bank_letter": d.name,
					"month": d.month,
					"year": d.year,
					"letter_date": d.letter_date,
					"opening_balance": opening,
					"installment": d.amount,
					"balance": balance,
				}
			).db_insert()

		frappe.db.set_value(
			"OHB Bank Loan",
			loan,
			{"paid_amount": total - balance, "balance_amount": balance},
			update_modified=False,
		)


def get_loan_installments(company, employees, period_end):
	"""{employee: loan details with `installment`} for approved, active loans that started on or
	before `period_end` and still have a balance."""
	if not employees:
		return {}

	loans = frappe.get_all(
		"OHB Bank Loan",
		filters={
			"docstatus": 1,
			"status": "Active",
			"company": company,
			"employee": ("in", list(employees)),
			"loan_date": ("<=", getdate(period_end)),
		},
		fields=["name", "employee", "bank", "ohb_account_no", "total_loan_amount", "monthly_installment"],
		order_by="loan_date",
	)
	paid = get_paid_amounts([d.name for d in loans])

	result = {}
	for loan in loans:
		balance = flt(loan.total_loan_amount) - paid.get(loan.name, 0)
		installment = min(flt(loan.monthly_installment), balance)
		if installment > 0 and loan.employee not in result:
			loan.installment = installment
			loan.balance = balance
			result[loan.employee] = loan
	return result
