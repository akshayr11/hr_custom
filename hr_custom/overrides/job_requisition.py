"""Job Requisition: Justification is mandatory for a non-budgeted position, and the positions of
a requisition are taken from its Labor Clearance (Used / Remaining Number).

Used on the clearance master is the running count: a requisition adds its positions to it (and
gives them back when rejected, cancelled, deleted or moved to another clearance), so a Used
entered on the master by hand is kept. Remaining = Total - Used.

Budgeted / Justification and the Labor Clearance link are site fields, so they are looked up by
name / label / options instead of being hard-coded.
"""

import frappe
from frappe import _
from frappe.utils import flt

DOCTYPE = "Job Requisition"
TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text", "Text Editor")
CLEARANCE = "Labor Clearance"
# requisitions in these statuses give their positions back to the clearance
RELEASED_STATUSES = ("Rejected", "Cancelled")


def validate(doc, method=None):
	validate_justification(doc)
	validate_clearance_positions(doc)


def on_update(doc, method=None):
	field = get_clearance_field(doc.meta)
	if not field:
		return
	old_clearance, old_positions = get_counted_positions(doc.get_doc_before_save(), field)
	new_clearance, new_positions = get_counted_positions(doc, field)
	if (old_clearance, old_positions) != (new_clearance, new_positions):
		adjust_used(old_clearance, -old_positions)
		adjust_used(new_clearance, new_positions)
	refresh_fetched_values(doc, field)


def on_trash(doc, method=None):
	field = get_clearance_field(doc.meta)
	if field:
		clearance, positions = get_counted_positions(doc, field)
		adjust_used(clearance, -positions)


def validate_justification(doc):
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


def get_clearance_field(meta):
	"""Fieldname of the Job Requisition's link to Labor Clearance, if the site has one."""
	if not frappe.db.exists("DocType", CLEARANCE):
		return None
	for df in meta.fields:
		if df.fieldtype == "Link" and df.options == CLEARANCE:
			return df.fieldname


def counts_against_clearance(doc):
	return (
		doc.docstatus < 2
		and doc.get("status") not in RELEASED_STATUSES
		and (doc.get("workflow_state") or "") not in RELEASED_STATUSES
	)


def get_counted_positions(doc, field):
	"""(clearance, positions) the requisition takes from its clearance; nothing when released."""
	if not doc or not doc.get(field) or not counts_against_clearance(doc):
		return None, 0
	return doc.get(field), flt(doc.no_of_positions)


def validate_clearance_positions(doc):
	"""A requisition cannot ask for more positions than its clearance still has."""
	field = get_clearance_field(doc.meta)
	clearance, positions = get_counted_positions(doc, field) if field else (None, 0)
	if not clearance:
		return

	values = frappe.db.get_value(CLEARANCE, clearance, ["total_number", "used"], as_dict=True) or {}
	total, used = flt(values.get("total_number")), flt(values.get("used"))
	# positions this requisition already holds on the same clearance are part of Used
	old_clearance, old_positions = get_counted_positions(doc.get_doc_before_save(), field)
	if old_clearance == clearance:
		used -= old_positions
	remaining = total - used
	if positions > remaining:
		frappe.throw(
			_("Labor Clearance {0} has only {1} of {2} positions remaining; this requisition asks for {3}.").format(
				frappe.bold(clearance), frappe.bold(f"{remaining:g}"), f"{total:g}", frappe.bold(f"{positions:g}")
			),
			title=_("Not Enough Positions"),
		)


def refresh_fetched_values(doc, field):
	"""Fields fetched from the clearance (e.g. Used / Pending) were set before Used was updated."""
	clearance = doc.get(field)
	values = {}
	for df in doc.meta.fields:
		source = (df.fetch_from or "").split(".")
		if len(source) == 2 and source[0] == field:
			values[df.fieldname] = frappe.db.get_value(CLEARANCE, clearance, source[1]) if clearance else None
	if values:
		doc.db_set(values, update_modified=False)


def adjust_used(clearance, positions):
	"""Used += positions on the clearance master, Remaining = Total - Used."""
	if not clearance or not positions or not frappe.db.exists(CLEARANCE, clearance):
		return
	values = frappe.db.get_value(CLEARANCE, clearance, ["total_number", "used"], as_dict=True, for_update=True)
	used = max(flt(values.used) + positions, 0)
	frappe.db.set_value(CLEARANCE, clearance, {"used": used, "remaining_number": flt(values.total_number) - used})
