"""Job Requisition: Justification is mandatory for a non-budgeted position, and the positions of
a requisition are taken from its Labor Clearance (Used / Remaining Number).

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
	before = doc.get_doc_before_save()
	update_clearances([doc.get(field), before and before.get(field)])
	refresh_fetched_values(doc, field)


def on_trash(doc, method=None):
	field = get_clearance_field(doc.meta)
	if field:
		update_clearances([doc.get(field)], exclude=doc.name)


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


def get_used_positions(clearance, field, exclude=None):
	jr = frappe.qb.DocType(DOCTYPE)
	query = (
		frappe.qb.from_(jr)
		.select(frappe.query_builder.functions.Sum(jr.no_of_positions))
		.where((jr[field] == clearance) & (jr.docstatus < 2) & (jr.status.notin(RELEASED_STATUSES)))
	)
	if frappe.get_meta(DOCTYPE).has_field("workflow_state"):
		query = query.where(jr.workflow_state.isnull() | jr.workflow_state.notin(RELEASED_STATUSES))
	if exclude:
		query = query.where(jr.name != exclude)
	return flt(query.run()[0][0])


def validate_clearance_positions(doc):
	"""A requisition cannot ask for more positions than its clearance still has."""
	field = get_clearance_field(doc.meta)
	clearance = field and doc.get(field)
	if not clearance or not counts_against_clearance(doc):
		return

	total = flt(frappe.db.get_value(CLEARANCE, clearance, "total_number"))
	used = get_used_positions(clearance, field, exclude=None if doc.is_new() else doc.name)
	remaining = total - used
	if flt(doc.no_of_positions) > remaining:
		frappe.throw(
			_("Labor Clearance {0} has only {1} of {2} positions remaining; this requisition asks for {3}.").format(
				frappe.bold(clearance), frappe.bold(f"{remaining:g}"), f"{total:g}", frappe.bold(f"{flt(doc.no_of_positions):g}")
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


def update_clearances(clearances, exclude=None):
	"""Used = positions of the requisitions linked to the clearance, Remaining = Total - Used."""
	field = get_clearance_field(frappe.get_meta(DOCTYPE))
	if not field:
		return
	for clearance in {c for c in clearances if c}:
		if not frappe.db.exists(CLEARANCE, clearance):
			continue
		used = get_used_positions(clearance, field, exclude=exclude)
		total = flt(frappe.db.get_value(CLEARANCE, clearance, "total_number"))
		frappe.db.set_value(CLEARANCE, clearance, {"used": used, "remaining_number": total - used})


@frappe.whitelist()
def recalculate_all_clearances():
	"""Fill Used / Remaining for existing clearances (run once after deploying)."""
	frappe.only_for(("System Manager", "HR Manager"))
	update_clearances(frappe.get_all(CLEARANCE, pluck="name"))
