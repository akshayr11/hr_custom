"""Job Requisition: Justification is mandatory for a non-budgeted position.

Budgeted / Justification are site custom fields (Customize Form), so they are looked up by name or
label ('budget', 'justif') instead of being hard-coded.
"""

import frappe
from frappe import _

DOCTYPE = "Job Requisition"
TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text", "Text Editor")


def validate(doc, method=None):
	budgeted, justification = get_fields(doc.meta)
	if not budgeted or not justification:
		return

	if is_non_budgeted(doc.get(budgeted.fieldname), budgeted.fieldtype) and not strip_html(
		doc.get(justification.fieldname)
	):
		frappe.throw(
			_("{0} is mandatory for a non-budgeted position").format(_(justification.label)),
			frappe.MandatoryError,
			title=_("Missing Justification"),
		)


def get_fields(meta):
	def find(keyword, fieldtypes):
		for df in meta.fields:
			if df.fieldtype in fieldtypes and (
				keyword in df.fieldname.lower() or keyword in (df.label or "").lower()
			):
				return df

	return find("budget", ("Select", "Check")), find("justif", TEXT_TYPES)


def is_non_budgeted(value, fieldtype):
	if fieldtype == "Check":
		return not frappe.utils.cint(value)
	return (value or "").strip().lower() in ("no", "non budgeted", "non-budgeted", "not budgeted")


def strip_html(value):
	return frappe.utils.strip_html(value or "").strip()


def make_fields():
	"""Show Justification as mandatory on the form when the position is not budgeted."""
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	budgeted, justification = get_fields(frappe.get_meta(DOCTYPE))
	if not budgeted or not justification:
		return

	condition = (
		f"eval:!doc.{budgeted.fieldname}"
		if budgeted.fieldtype == "Check"
		else f"eval:(doc.{budgeted.fieldname} || '').toLowerCase() == 'no'"
	)
	make_property_setter(
		DOCTYPE,
		justification.fieldname,
		"mandatory_depends_on",
		condition,
		"Code",
		validate_fields_for_doctype=False,
	)
