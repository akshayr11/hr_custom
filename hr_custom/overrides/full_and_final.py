"""Gratuity paid in instalments through payroll while the employee is still working.

The instalments are paid with a salary component ticked "Is Gratuity Instalment" (setup creates
"Gratuity Instalment"), e.g. through an Additional Salary. The Full and Final Statement lists
the submitted salary slips that paid it under "Gratuity Paid through Payroll", and the Gratuity
row of its Payables is the balance: Gratuity amount - instalments already paid.

The list is refreshed on every save of a draft statement, and when a salary slip with an
instalment is submitted or cancelled.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt, fmt_money

GRATUITY_INSTALMENT_COMPONENT = "Gratuity Instalment"
GRATUITY_INSTALMENT_ABBR = "GI"
FNF = "Full and Final Statement"


def validate(doc, method=None):
	"""Full and Final Statement validate."""
	if doc.docstatus == 0 and doc.meta.has_field("gratuity_instalments"):
		set_gratuity_instalments(doc)


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
		row.remark = _("Gratuity {0} less {1} already paid through payroll").format(
			fmt_money(gratuity, currency=currency), fmt_money(paid, currency=currency)
		)
		paid = max(paid - gratuity, 0)  # more than one Gratuity: the rest goes to the next one

	if has_gratuity and paid > 0:
		frappe.msgprint(
			_("The gratuity instalments paid through payroll are {0} more than the Gratuity. Add it to Receivables to recover it.").format(
				fmt_money(paid, currency=frappe.get_cached_value("Company", doc.company, "default_currency") if doc.company else None)
			),
			title=_("Gratuity Overpaid"),
			indicator="orange",
		)

	if hasattr(doc, "set_totals"):
		doc.set_totals()


def on_salary_slip_change(doc, method=None):
	"""Salary Slip on_submit / on_cancel: refresh the employee's draft Full and Final Statement."""
	components = get_instalment_components()
	if not components or not any(d.salary_component in components for d in doc.get("earnings") or []):
		return
	if not frappe.db.exists("DocType", FNF):
		return

	for name in frappe.get_all(FNF, filters={"employee": doc.employee, "docstatus": 0}, pluck="name"):
		try:
			statement = frappe.get_doc(FNF, name)
			# before save: the links are validated first and the cancelled slip must be gone
			set_gratuity_instalments(statement)
			statement.flags.ignore_permissions = True
			statement.save()
		except Exception:
			frappe.log_error(title=f"Full and Final Statement {name}: gratuity instalments not refreshed")


def make_fields():
	"""Is Gratuity Instalment on Salary Component, the Gratuity Instalment component, and the
	Gratuity Paid through Payroll section on Full and Final Statement."""
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "is_gratuity_instalment",
					"fieldtype": "Check",
					"label": "Is Gratuity Instalment",
					"insert_after": "is_overtime_component",
					"depends_on": "eval:doc.type=='Earning'",
					"description": "Gratuity paid in parts through payroll while the employee is working; shown as already paid in the Full and Final Statement",
				}
			],
			FNF: [
				{
					"fieldname": "gratuity_instalments_section",
					"fieldtype": "Section Break",
					"label": "Gratuity Paid through Payroll",
					"insert_after": "payables",
				},
				{
					"fieldname": "gratuity_instalments",
					"fieldtype": "Table",
					"label": "Gratuity Instalments",
					"options": "Full and Final Gratuity Instalment",
					"insert_after": "gratuity_instalments_section",
					"read_only": 1,
					"description": "Submitted salary slips with a Gratuity Instalment component. The Gratuity in Payables is the balance after these.",
				},
				{
					"fieldname": "total_gratuity_instalments",
					"fieldtype": "Currency",
					"label": "Gratuity Already Paid",
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
	if frappe.db.exists("Salary Component", GRATUITY_INSTALMENT_COMPONENT):
		frappe.db.set_value("Salary Component", GRATUITY_INSTALMENT_COMPONENT, "is_gratuity_instalment", 1)
		return
	frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": GRATUITY_INSTALMENT_COMPONENT,
			"salary_component_abbr": GRATUITY_INSTALMENT_ABBR,
			"type": "Earning",
			"depends_on_payment_days": 0,
			"remove_if_zero_valued": 1,
			"is_gratuity_instalment": 1,
			"description": _("Gratuity paid in parts through payroll (Additional Salary) while the employee is still working"),
		}
	).insert(ignore_permissions=True)
