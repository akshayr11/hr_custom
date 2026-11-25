"""Partial payments of a Full and Final Statement.

HRMS pays a statement with one journal entry for the whole amount and marks it Paid as soon as
any journal entry refers to it. Here it can be paid in parts:

* Make Payment (submitted, Unpaid / Partly Paid statements) asks for an amount and makes a Bank
  Entry for it: every payable / receivable / asset recovery line of the settlement (the lines of
  HRMS's own journal entry) is cleared by the same share of what is still open on it, and the
  line referring to the statement (the bank line, account chosen by the user) is the amount.
  The last payment clears exactly what is left.
* Paid Amount = the statement's lines of the submitted journal entries (credit - debit),
  Outstanding Amount = settlement net - paid; status Unpaid, Partly Paid or Paid. Updated on
  journal entry submit / cancel, after HRMS's own update (which sets Paid on any entry).
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import flt, today

FNF = "Full and Final Statement"
STATUS_OPTIONS = "Paid\nPartly Paid\nUnpaid\nCancelled"


def precision():
	return frappe.get_precision("Journal Entry Account", "debit_in_account_currency") or 3


def get_settlement_lines(statement):
	"""{(account, party_type, party, side): [amount, remark]} of the settlement's lines (HRMS's
	journal entry for the statement without its balancing line)."""
	lines = {}
	for row in statement.create_journal_entry().accounts:
		if row.reference_type == FNF:
			continue
		for side, field in (("debit", "debit_in_account_currency"), ("credit", "credit_in_account_currency")):
			if flt(row.get(field)):
				key = (row.account, row.party_type or None, row.party or None, side)
				lines.setdefault(key, [0, row.user_remark])[0] += flt(row.get(field))
	return lines


def get_posted_lines(statement_name, docstatus=1):
	"""Same keys: what the statement's journal entries already cleared, and the amount paid."""
	jea = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")
	parents = (
		frappe.qb.from_(jea)
		.join(je)
		.on(jea.parent == je.name)
		.select(jea.parent)
		.distinct()
		.where((jea.reference_type == FNF) & (jea.reference_name == statement_name) & (je.docstatus == docstatus))
		.run(pluck=True)
	)
	posted, paid = {}, 0
	for row in frappe.get_all(
		"Journal Entry Account",
		filters={"parent": ("in", parents or [""]), "parenttype": "Journal Entry"},
		fields=["account", "party_type", "party", "debit_in_account_currency", "credit_in_account_currency", "reference_type", "reference_name"],
	):
		if row.reference_type == FNF and row.reference_name == statement_name:
			paid += flt(row.credit_in_account_currency) - flt(row.debit_in_account_currency)
			continue
		for side, field in (("debit", "debit_in_account_currency"), ("credit", "credit_in_account_currency")):
			if flt(row.get(field)):
				key = (row.account, row.party_type or None, row.party or None, side)
				posted[key] = posted.get(key, 0) + flt(row.get(field))
	return posted, paid


def get_net(lines):
	return flt(sum(v[0] if k[3] == "debit" else -v[0] for k, v in lines.items()), precision())


@frappe.whitelist()
def make_payment(statement: str, amount: float):
	"""Bank Entry paying `amount` of the statement (not saved; opened in the form)."""
	doc = frappe.get_doc(FNF, statement)
	doc.check_permission("read")
	frappe.has_permission("Journal Entry", "create", throw=True)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Full and Final Statement first"))
	if frappe.db.exists("Journal Entry Account", {"reference_type": FNF, "reference_name": doc.name, "docstatus": 0}):
		frappe.throw(_("A draft Journal Entry for this statement exists. Submit or delete it first."))

	prec = precision()
	lines = get_settlement_lines(doc)
	posted, _paid = get_posted_lines(doc.name)
	remaining = {k: [flt(v[0] - posted.get(k, 0), prec), v[1]] for k, v in lines.items()}
	outstanding = get_net(remaining)
	amount = flt(amount, prec)
	if outstanding <= 0:
		frappe.throw(_("Nothing is left to pay on this statement"))
	if amount <= 0 or amount > outstanding:
		frappe.throw(_("Amount must be more than 0 and at most the outstanding {0}").format(outstanding))

	share = amount / outstanding
	jv = frappe.new_doc("Journal Entry")
	jv.company = doc.company
	jv.voucher_type = "Bank Entry"
	jv.posting_date = today()
	jv.user_remark = _("Full and Final Settlement {0} of {1}: payment {2} of {3}").format(
		doc.name, doc.employee_name or doc.employee, amount, outstanding
	)
	rows = []
	for (account, party_type, party, side), (value, remark) in remaining.items():
		value = flt(value * share, prec) if share < 1 else value
		if value <= 0:
			continue
		row = jv.append(
			"accounts",
			{
				"account": account,
				f"{side}_in_account_currency": value,
				"party_type": party_type,
				"party": party,
				"user_remark": remark,
			},
		)
		rows.append((row, side))

	# rounding: the lines add up to the amount
	difference = flt(amount - sum(flt(r.debit_in_account_currency) - flt(r.credit_in_account_currency) for r, _s in rows), prec)
	if difference:
		row = max((r for r, s in rows if s == "debit"), key=lambda r: flt(r.debit_in_account_currency), default=None)
		if row:
			row.debit_in_account_currency = flt(row.debit_in_account_currency + difference, prec)

	jv.append(
		"accounts",
		{"credit_in_account_currency": amount, "reference_type": FNF, "reference_name": doc.name},
	)
	return jv


def update_payment_status(statement_name):
	doc = frappe.get_doc(FNF, statement_name)
	if doc.docstatus != 1 or not doc.meta.has_field("paid_amount"):
		return
	net = get_net(get_settlement_lines(doc))
	_posted, paid = get_posted_lines(doc.name)
	paid = flt(paid, precision())
	outstanding = flt(net - paid, precision())

	if paid and outstanding <= 0:
		status = "Paid"
	elif paid:
		status = "Partly Paid"
	else:
		status = "Unpaid"
	doc.db_set({"paid_amount": paid, "outstanding_amount": max(outstanding, 0), "status": status})
	doc.update_linked_payable_documents()  # Gratuity / Leave Encashment paid only when fully Paid
	doc.notify_update()


def on_journal_entry_change(doc, method=None):
	"""Journal Entry on_submit / on_cancel (after HRMS's update_full_and_final_statement_status)."""
	for name in {d.reference_name for d in doc.accounts if d.reference_type == FNF and d.reference_name}:
		update_payment_status(name)


def set_outstanding(doc, method=None):
	"""Full and Final Statement validate (draft) / on_submit: nothing paid yet."""
	if not doc.meta.has_field("paid_amount"):
		return
	if doc.docstatus == 0:
		doc.paid_amount = 0
		doc.outstanding_amount = max(get_net(get_settlement_lines(doc)), 0)
	elif doc.docstatus == 1:
		update_payment_status(doc.name)


def make_fields():
	create_custom_fields(
		{
			FNF: [
				{
					"fieldname": "paid_amount",
					"fieldtype": "Currency",
					"label": "Paid Amount",
					"insert_after": "total_receivable_amount",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"description": "Paid through the statement's journal entries (Make Payment)",
				},
				{
					"fieldname": "outstanding_amount",
					"fieldtype": "Currency",
					"label": "Outstanding Amount",
					"insert_after": "paid_amount",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"bold": 1,
				},
			]
		},
		update=True,
	)
	make_property_setter(FNF, "status", "options", STATUS_OPTIONS, "Text", validate_fields_for_doctype=False)
