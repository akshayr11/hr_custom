"""Employee Promotion: warn when the Promotion Date is backdated or falls in a payroll period that is
already processed for the employee (salary slip / payroll entry), so the user can change the date."""

import frappe
from frappe import _
from frappe.utils import formatdate, get_link_to_form, getdate, today


def validate(doc, method=None):
	if doc.docstatus != 0:
		return
	warnings = get_promotion_date_warnings(doc.employee, doc.promotion_date)
	if warnings:
		frappe.msgprint(
			"<br><br>".join(warnings) + "<br><br>" + _("Please change the Promotion Date if this is not intended."),
			title=_("Check Promotion Date"),
			indicator="orange",
		)


@frappe.whitelist()
def get_promotion_date_warnings(employee, promotion_date):
	if not employee or not promotion_date:
		return []

	date = getdate(promotion_date)
	warnings = []
	if date < getdate(today()):
		warnings.append(_("Promotion Date {0} is a back date.").format(frappe.bold(formatdate(date))))

	payroll = get_processed_payroll(employee, date)
	if payroll:
		warnings.append(
			_("Payroll for {0} to {1} is already created for this employee ({2}).").format(
				frappe.bold(formatdate(payroll.start_date)),
				frappe.bold(formatdate(payroll.end_date)),
				get_link_to_form(payroll.doctype, payroll.name),
			)
		)
	return warnings


def get_processed_payroll(employee, date):
	"""Salary slip of the employee covering the date, else a payroll entry that includes them."""
	slip = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": ("<", 2), "start_date": ("<=", date), "end_date": (">=", date)},
		["name", "start_date", "end_date"],
		as_dict=True,
	)
	if slip:
		return frappe._dict(slip, doctype="Salary Slip")

	pe = frappe.qb.DocType("Payroll Entry")
	ped = frappe.qb.DocType("Payroll Employee Detail")
	entry = (
		frappe.qb.from_(pe)
		.join(ped)
		.on((ped.parent == pe.name) & (ped.parenttype == "Payroll Entry"))
		.select(pe.name, pe.start_date, pe.end_date)
		.where((ped.employee == employee) & (pe.docstatus < 2) & (pe.start_date <= date) & (pe.end_date >= date))
		.limit(1)
	).run(as_dict=True)
	if entry:
		return frappe._dict(entry[0], doctype="Payroll Entry")
