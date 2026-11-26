"""Prepaid Gratuity: gratuity paid in advance through payroll while the employee is still working.

It is paid with a salary component ticked "Is Prepaid Gratuity" (setup creates "Prepaid
Gratuity"), either as a component of the salary structure for the remaining payroll months or as
Additional Salary for selected months. The Gratuity (hr_custom.overrides.gratuity) and the Full
and Final Statement list the submitted salary slips that paid it under "Prepaid Gratuity", and
the Gratuity row of the statement's Payables is the balance: Gratuity amount - prepaid.

The list is refreshed on every save of a draft statement, and when a salary slip with an
instalment is submitted or cancelled.

Final salary: the employee's salary slips from the relieving month on (and withheld ones, as
HRMS does) are Payables rows "Salary Slip" linked to the slip, Paid via Salary Slip (the
statement's journal entry leaves them out: payroll pays them). A row is Settled once its
Payroll Entry's bank entry is submitted, else Unsettled with a remark, so the statement cannot
be submitted before the final salary is paid. Refreshed on save of a draft statement, on salary
slip submit / cancel and on payroll bank entry submit / cancel.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt, fmt_money, get_first_day

GRATUITY_INSTALMENT_COMPONENT = "Prepaid Gratuity"
GRATUITY_INSTALMENT_ABBR = "PG"
# the component's name before it was renamed to Prepaid Gratuity
OLD_COMPONENT = "Gratuity Instalment"
FNF = "Full and Final Statement"


def validate(doc, method=None):
	"""Full and Final Statement validate."""
	if doc.docstatus != 0:
		set_payable_total(doc)  # HRMS works the totals out again on submit
		return
	set_salary_slip_payables(doc)
	if doc.meta.has_field("gratuity_instalments"):
		set_gratuity_instalments(doc)
	set_payable_total(doc)


def set_payable_total(doc):
	"""Total Payable without the rows paid via salary slip: payroll pays them, not the statement
	(HRMS's Create Journal Entry balances on this total but leaves those rows out)."""
	if hasattr(doc, "set_totals"):
		doc.set_totals()
	via_slip = sum(flt(row.amount) for row in doc.get("payables") or [] if row.paid_via_salary_slip)
	if via_slip:
		doc.total_payable_amount = flt(
			flt(doc.total_payable_amount) - via_slip, doc.precision("total_payable_amount")
		)


def set_salary_slip_payables(doc):
	"""Payables rows of the final salary slips (rebuilt; other rows are kept)."""
	if not (doc.employee and doc.relieving_date):
		return
	slips = get_final_salary_slips(doc.employee, doc.relieving_date)
	others = [row for row in doc.get("payables") or [] if row.reference_document_type != "Salary Slip"]

	rows = []
	for slip in slips:
		paid, remark = get_slip_payment(slip)
		rows.append(
			{
				"component": "Salary Slip",
				"reference_document_type": "Salary Slip",
				"reference_document": slip.name,
				"amount": slip.net_pay,
				"account": slip.payroll_payable_account,
				"paid_via_salary_slip": 1,
				"status": "Settled" if paid else "Unsettled",
				"remark": remark,
			}
		)
	doc.set("payables", [])
	for row in rows + others:
		doc.append("payables", row if isinstance(row, dict) else row.as_dict(no_default_fields=True))

	drafts = frappe.get_all(
		"Salary Slip",
		filters={"employee": doc.employee, "docstatus": 0, "end_date": (">=", get_first_day(doc.relieving_date))},
		pluck="name",
	)
	if drafts:
		frappe.msgprint(
			_("Salary Slip {0} of the final month is not submitted yet").format(", ".join(drafts)),
			indicator="orange",
			alert=True,
		)
	if hasattr(doc, "set_totals"):
		doc.set_totals()


def get_final_salary_slips(employee, relieving_date):
	"""Submitted salary slips from the relieving month on, and withheld ones."""
	slip = frappe.qb.DocType("Salary Slip")
	pe = frappe.qb.DocType("Payroll Entry")
	return (
		frappe.qb.from_(slip)
		.left_join(pe)
		.on(slip.payroll_entry == pe.name)
		.select(
			slip.name, slip.status, slip.net_pay, slip.payroll_entry, slip.start_date, pe.payroll_payable_account
		)
		.where(
			(slip.employee == employee)
			& (slip.docstatus == 1)
			& ((slip.end_date >= get_first_day(relieving_date)) | (slip.status == "Withheld"))
		)
		.orderby(slip.start_date)
		.run(as_dict=True)
	)


def get_slip_payment(slip):
	"""(paid, remark): paid once the slip's Payroll Entry has a submitted bank entry."""
	if slip.status == "Withheld":
		return False, _("Salary withheld: release it from Payroll Entry {0}").format(slip.payroll_entry or "")
	if not slip.payroll_entry:
		return False, _("Not paid: the salary slip is not part of a Payroll Entry")

	jea = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")
	bank_entry = (
		frappe.qb.from_(jea)
		.join(je)
		.on(jea.parent == je.name)
		.select(je.name)
		.where(
			(jea.reference_type == "Payroll Entry")
			& (jea.reference_name == slip.payroll_entry)
			& (je.voucher_type == "Bank Entry")
			& (je.docstatus == 1)
		)
		.limit(1)
		.run(pluck=True)
	)
	if bank_entry:
		return True, _("Paid through Payroll Entry {0} by {1}").format(slip.payroll_entry, bank_entry[0])
	return False, _("Not paid yet: make the bank entry of Payroll Entry {0}").format(slip.payroll_entry)


def set_gratuity_instalments(doc):
	doc.set("gratuity_instalments", get_gratuity_instalments(doc.employee))
	doc.total_gratuity_instalments = flt(sum(flt(d.amount) for d in doc.gratuity_instalments))
	set_gratuity_balance(doc)


def get_gratuity_instalments(employee):
	"""Instalment earnings of the employee's submitted salary slips."""
	components = get_instalment_components()
	if not (employee and components):
		return []

	slip = frappe.qb.DocType("Salary Slip")
	detail = frappe.qb.DocType("Salary Detail")
	rows = (
		frappe.qb.from_(detail)
		.join(slip)
		.on(detail.parent == slip.name)
		.select(
			slip.name.as_("salary_slip"),
			slip.payroll_entry,
			slip.start_date,
			slip.end_date,
			detail.salary_component,
			detail.amount,
		)
		.where(
			(slip.employee == employee)
			& (slip.docstatus == 1)
			& (detail.parenttype == "Salary Slip")
			& (detail.parentfield == "earnings")
			& (detail.salary_component.isin(components))
			& (detail.amount != 0)
		)
		.orderby(slip.start_date)
		.run(as_dict=True)
	)
	return rows


def get_instalment_components():
	if not frappe.get_meta("Salary Component").has_field("is_gratuity_instalment"):
		return []
	return frappe.get_all("Salary Component", filters={"is_gratuity_instalment": 1}, pluck="name")


def set_gratuity_balance(doc):
	"""Gratuity payable = the Gratuity's amount - the instalments already paid."""
	paid = flt(doc.total_gratuity_instalments)
	has_gratuity = False
	for row in doc.get("payables") or []:
		if row.reference_document_type != "Gratuity" or not row.reference_document:
			continue
		has_gratuity = True
		gratuity = flt(frappe.db.get_value("Gratuity", row.reference_document, "amount"))
		if not paid:
			row.amount = gratuity
			continue
		row.amount = max(gratuity - paid, 0)
		currency = frappe.get_cached_value("Company", doc.company, "default_currency") if doc.company else None
		row.remark = _("Gratuity {0} less {1} Prepaid Gratuity paid through payroll").format(
			fmt_money(gratuity, currency=currency), fmt_money(paid, currency=currency)
		)
		paid = max(paid - gratuity, 0)  # more than one Gratuity: the rest goes to the next one

	if has_gratuity and paid > 0:
		frappe.msgprint(
			_("The Prepaid Gratuity paid through payroll is {0} more than the Gratuity. Add it to Receivables to recover it.").format(
				fmt_money(paid, currency=frappe.get_cached_value("Company", doc.company, "default_currency") if doc.company else None)
			),
			title=_("Gratuity Overpaid"),
			indicator="orange",
		)

	if hasattr(doc, "set_totals"):
		doc.set_totals()


def on_salary_slip_change(doc, method=None):
	"""Salary Slip on_submit / on_cancel: refresh the employee's draft Full and Final Statement."""
	refresh_draft_statements([doc.employee])


def on_payroll_bank_entry_change(doc, method=None):
	"""Journal Entry on_submit / on_cancel: a payroll bank entry settles the final salary slips."""
	payroll_entries = {d.reference_name for d in doc.accounts if d.reference_type == "Payroll Entry" and d.reference_name}
	if doc.voucher_type != "Bank Entry" or not payroll_entries:
		return
	employees = frappe.get_all(
		"Salary Slip", filters={"payroll_entry": ("in", list(payroll_entries)), "docstatus": 1}, pluck="employee"
	)
	refresh_draft_statements(employees)


def refresh_draft_statements(employees):
	if not employees or not frappe.db.exists("DocType", FNF):
		return
	for name in frappe.get_all(FNF, filters={"employee": ("in", list(set(employees))), "docstatus": 0}, pluck="name"):
		try:
			statement = frappe.get_doc(FNF, name)
			# before save: the links are validated first and a cancelled slip must be gone
			set_salary_slip_payables(statement)
			if statement.meta.has_field("gratuity_instalments"):
				set_gratuity_instalments(statement)
			statement.flags.ignore_permissions = True
			statement.save()
		except Exception:
			frappe.log_error(title=f"Full and Final Statement {name}: salary slips not refreshed")


def make_fields():
	"""Is Gratuity Instalment on Salary Component, the Gratuity Instalment component, and the
	Gratuity Paid through Payroll section on Full and Final Statement."""
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "is_gratuity_instalment",
					"fieldtype": "Check",
					"label": "Is Prepaid Gratuity",
					"insert_after": "is_overtime_component",
					"depends_on": "eval:doc.type=='Earning'",
					"description": "Gratuity paid in advance through payroll (structure component or Additional Salary); shown as Prepaid on the Gratuity and deducted in the Full and Final Statement",
				}
			],
			FNF: [
				{
					"fieldname": "gratuity_instalments_section",
					"fieldtype": "Section Break",
					"label": "Prepaid Gratuity (Paid through Payroll)",
					"insert_after": "payables",
				},
				{
					"fieldname": "gratuity_instalments",
					"fieldtype": "Table",
					"label": "Prepaid Gratuity",
					"options": "Full and Final Gratuity Instalment",
					"insert_after": "gratuity_instalments_section",
					"read_only": 1,
					"description": "Submitted salary slips with a Prepaid Gratuity component. The Gratuity in Payables is the balance after these.",
				},
				{
					"fieldname": "total_gratuity_instalments",
					"fieldtype": "Currency",
					"label": "Prepaid Gratuity Amount",
					"insert_after": "gratuity_instalments",
					"read_only": 1,
					"bold": 1,
				},
			],
		},
		update=True,
	)
	make_gratuity_instalment_component()


def make_gratuity_instalment_component():
	"""The Prepaid Gratuity component (the earlier "Gratuity Instalment" is renamed when unused)."""
	name = GRATUITY_INSTALMENT_COMPONENT
	if not frappe.db.exists("Salary Component", name) and frappe.db.exists("Salary Component", OLD_COMPONENT):
		if is_component_used(OLD_COMPONENT):
			print(f"{OLD_COMPONENT} is used in salary slips / structures: kept (it still counts as Prepaid Gratuity)")
			frappe.db.set_value("Salary Component", OLD_COMPONENT, "is_gratuity_instalment", 1)
		else:
			frappe.rename_doc("Salary Component", OLD_COMPONENT, name, force=True)
			frappe.db.set_value("Salary Component", name, "salary_component", name)
			if not frappe.db.exists("Salary Component", {"salary_component_abbr": GRATUITY_INSTALMENT_ABBR}):
				frappe.db.set_value("Salary Component", name, "salary_component_abbr", GRATUITY_INSTALMENT_ABBR)
			print(f"Renamed {OLD_COMPONENT} to {name}")

	if frappe.db.exists("Salary Component", name):
		frappe.db.set_value("Salary Component", name, "is_gratuity_instalment", 1)
		return
	abbr = GRATUITY_INSTALMENT_ABBR
	if frappe.db.exists("Salary Component", {"salary_component_abbr": abbr}):
		abbr = "PGR"
	frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": name,
			"salary_component_abbr": abbr,
			"type": "Earning",
			"depends_on_payment_days": 0,
			"remove_if_zero_valued": 1,
			"is_gratuity_instalment": 1,
			"description": _(
				"Gratuity paid in advance through payroll (salary structure or Additional Salary) while the employee is still working"
			),
		}
	).insert(ignore_permissions=True)
	print(f"Created {name}")


def is_component_used(component):
	return bool(
		frappe.db.exists("Salary Detail", {"salary_component": component})
		or frappe.db.exists("Additional Salary", {"salary_component": component})
	)
