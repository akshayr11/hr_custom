"""Lending: repayment schedules of 'Advance Salary' loans are reviewed before they become active.

Normally submitting a Loan Disbursement submits its Loan Repayment Schedule and makes it Active. For
loan products with 'Review Repayment Schedule Before Activation' (set for Advance Salary), the
schedule is left in Draft instead. The user can then change its rows (skip a month by removing the
row or setting it to 0, change dates, split the amount unevenly) and Activate (submit) it. Until
then no demand / accrual / salary deduction is made, since Lending only processes Active schedules.

While the schedule is in Draft, the rows entered by the user are kept (Lending would rebuild them
from the loan terms on every save); balances are recalculated and the principal must add up to the
disbursed amount.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate

SCHEDULE = "Loan Repayment Schedule"
REVIEW_FIELD = "review_repayment_schedule"
DRAFT = "Draft"


def needs_review(loan_product):
	if not loan_product:
		return False
	if frappe.get_meta("Loan Product").has_field(REVIEW_FIELD):
		return bool(frappe.db.get_value("Loan Product", loan_product, REVIEW_FIELD))
	return is_advance_salary(loan_product)


def is_advance_salary(loan_product):
	product_name = frappe.db.get_value("Loan Product", loan_product, "product_name") or ""
	return "advance salary" in f"{loan_product} {product_name}".lower()


class LoanDisbursementMixin:
	def needs_schedule_review(self):
		return needs_review(frappe.db.get_value("Loan", self.against_loan, "loan_product"))

	def has_submitted_schedule(self):
		return frappe.db.exists(
			SCHEDULE, {"loan": self.against_loan, "loan_disbursement": self.name, "docstatus": 1}
		)

	def submit_repayment_schedule(self):
		if not self.needs_schedule_review():
			return super().submit_repayment_schedule()

		schedule = frappe.db.get_value(
			SCHEDULE, {"loan": self.against_loan, "loan_disbursement": self.name, "docstatus": 0}
		)
		if schedule:
			frappe.db.set_value(SCHEDULE, schedule, "status", DRAFT)
			frappe.msgprint(
				_("Repayment Schedule {0} is in Draft. Review it and click Activate to start the repayments.").format(
					frappe.utils.get_link_to_form(SCHEDULE, schedule)
				),
				alert=True,
			)

	def update_repayment_schedule_status(self, cancel=0):
		# nothing to switch while the reviewed schedule is still in Draft
		if self.needs_schedule_review() and not self.has_submitted_schedule():
			return
		return super().update_repayment_schedule_status(cancel=cancel)

	def update_current_repayment_schedule(self):
		if self.needs_schedule_review() and not self.has_submitted_schedule():
			return
		return super().update_current_repayment_schedule()

	def on_cancel(self):
		super().on_cancel()
		if self.needs_schedule_review():
			for name in frappe.get_all(
				SCHEDULE,
				{"loan": self.against_loan, "loan_disbursement": self.name, "docstatus": 0},
				pluck="name",
			):
				frappe.delete_doc(SCHEDULE, name, ignore_permissions=True, force=True)


class LoanRepaymentScheduleMixin:
	def onload(self):
		if hasattr(super(), "onload"):
			super().onload()
		self.set_onload("review_schedule", self.is_under_review())

	def is_under_review(self):
		return self.status == DRAFT and bool(self.get("repayment_schedule")) and needs_review(self.loan_product)

	def validate(self):
		if self.is_under_review():
			self.validate_reviewed_schedule()
		else:
			super().validate()

	def validate_reviewed_schedule(self):
		amount = flt(self.current_principal_amount or self.disbursed_amount)
		precision = self.precision("disbursed_amount") or 2

		# a month set to 0 is skipped
		rows = [d for d in self.repayment_schedule if flt(d.principal_amount) or flt(d.interest_amount)]
		for d in rows:
			if not d.payment_date:
				frappe.throw(_("Row {0}: Payment Date is mandatory").format(d.idx))
			if flt(d.principal_amount) < 0:
				frappe.throw(_("Row {0}: Principal Amount cannot be negative").format(d.idx))
			if self.posting_date and getdate(d.payment_date) < getdate(self.posting_date):
				frappe.throw(_("Row {0}: Payment Date cannot be before the disbursement").format(d.idx))

		dates = [getdate(d.payment_date) for d in rows]
		if len(dates) != len(set(dates)):
			frappe.throw(_("Two rows have the same Payment Date. Combine them into one row."))

		total = flt(sum(flt(d.principal_amount) for d in rows), precision)
		currency = frappe.get_cached_value("Company", self.company, "default_currency") if self.get("company") else None
		if abs(total - flt(amount, precision)) > 0.5 / 10**precision:
			frappe.throw(
				_("Total Principal Amount {0} must be equal to the disbursed amount {1} (difference {2})").format(
					frappe.bold(fmt_money(total, precision, currency)),
					frappe.bold(fmt_money(amount, precision, currency)),
					fmt_money(amount - total, precision, currency),
				),
				title=_("Repayment Schedule does not match"),
			)

		rows.sort(key=lambda d: getdate(d.payment_date))
		balance = amount
		for d in rows:
			d.total_payment = flt(d.principal_amount) + flt(d.interest_amount)
			balance = flt(balance - flt(d.principal_amount), precision)
			d.balance_loan_amount = balance

		self.set("repayment_schedule", rows)
		self.reset_index()
		self.set_maturity_date()
		self.repayment_periods = len(rows)
		if rows:
			self.repayment_start_date = rows[0].payment_date

	def before_submit(self):
		if hasattr(super(), "before_submit"):
			super().before_submit()
		if self.is_under_review():
			if frappe.db.get_value("Loan Disbursement", self.loan_disbursement, "docstatus") != 1:
				frappe.throw(_("Submit the Loan Disbursement {0} first").format(self.loan_disbursement))
			self.flags.activated_after_review = True
			self.status = "Active"

	def on_submit(self):
		super().on_submit()
		if self.flags.activated_after_review:
			# what Lending does for the schedule on disbursement submit: mark it (and older ones)
			frappe.get_doc("Loan Disbursement", self.loan_disbursement).update_current_repayment_schedule()


def make_fields():
	"""'Review Repayment Schedule Before Activation' on Loan Product, on for Advance Salary products."""
	if not frappe.db.exists("DocType", "Loan Product"):
		return

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Loan Product": [
				{
					"fieldname": REVIEW_FIELD,
					"fieldtype": "Check",
					"label": "Review Repayment Schedule Before Activation",
					"insert_after": "is_term_loan",
					"depends_on": "is_term_loan",
					"description": "The repayment schedule stays in Draft after disbursement so months can be "
					"skipped or amounts changed; it starts once it is Activated.",
				}
			]
		},
		update=True,
	)
	for product in frappe.get_all("Loan Product", pluck="name"):
		if is_advance_salary(product) and not frappe.db.get_value("Loan Product", product, REVIEW_FIELD):
			frappe.db.set_value("Loan Product", product, REVIEW_FIELD, 1)
