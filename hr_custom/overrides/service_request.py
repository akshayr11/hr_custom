"""Service Request (doctype owned by another app / created in the UI) - rules added from hr_custom:

1. Cost Center must belong to the selected Company (the form filters it too).
2. Rejecting needs Rejection Remarks.
3. Closing needs Closure Remarks.

Field names are looked up from the doctype instead of being hard-coded, because the doctype is
not part of this app.
"""

import frappe
from frappe import _

DOCTYPE = "Service Request"
REJECTION_REMARKS = "rejection_remarks"
CLOSURE_REMARKS = "closure_remarks"


def validate(doc, method=None):
	validate_cost_center_company(doc)
	validate_remarks(doc)


def validate_cost_center_company(doc):
	company_field = get_link_field(doc.meta, "Company")
	if not company_field or not doc.get(company_field):
		return

	company = doc.get(company_field)
	for df in doc.meta.get("fields", {"fieldtype": "Link", "options": "Cost Center"}):
		cost_center = doc.get(df.fieldname)
		if cost_center and frappe.db.get_value("Cost Center", cost_center, "company") != company:
			frappe.throw(
				_("{0} {1} does not belong to Company {2}").format(
					_(df.label), frappe.bold(cost_center), frappe.bold(company)
				)
			)


def validate_remarks(doc):
	state = (get_state(doc) or "").lower()
	if not state:
		return

	if "reject" in state:
		require_remarks(doc, get_remarks_field(doc.meta, "reject") or REJECTION_REMARKS, _("rejecting"))
	elif "close" in state:
		require_remarks(doc, get_remarks_field(doc.meta, "closure") or CLOSURE_REMARKS, _("closing"))


def require_remarks(doc, fieldname, action):
	if doc.meta.has_field(fieldname) and not (doc.get(fieldname) or "").strip():
		frappe.throw(
			_("{0} is mandatory when {1} the request").format(_(doc.meta.get_label(fieldname)), action),
			frappe.MandatoryError,
		)


def get_state(doc):
	"""Workflow state if the doctype has an active workflow, else its Status field."""
	from frappe.model.workflow import get_workflow_name, get_workflow_state_field

	workflow = get_workflow_name(doc.doctype)
	if workflow:
		return doc.get(get_workflow_state_field(workflow))
	return doc.get("status")


def get_link_field(meta, options):
	fields = meta.get("fields", {"fieldtype": "Link", "options": options})
	return fields[0].fieldname if fields else None


def get_remarks_field(meta, keyword):
	"""Existing text field like 'rejection_remarks' / 'closure_remarks' (any name containing keyword)."""
	for df in meta.fields:
		if df.fieldtype in ("Small Text", "Text", "Long Text", "Text Editor", "Data") and keyword in df.fieldname:
			return df.fieldname


def make_fields():
	"""Add Rejection Remarks (and Closure Remarks if missing). Skipped on sites without the doctype."""
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	meta = frappe.get_meta(DOCTYPE)
	closure_field = get_remarks_field(meta, "closure")
	fields = []
	if not closure_field:
		closure_field = CLOSURE_REMARKS
		fields.append(
			{
				"fieldname": CLOSURE_REMARKS,
				"fieldtype": "Small Text",
				"label": "Closure Remarks",
				"insert_after": meta.fields[-1].fieldname if meta.fields else None,
				"allow_on_submit": 1,
			}
		)
	if not get_remarks_field(meta, "reject"):
		fields.append(
			{
				"fieldname": REJECTION_REMARKS,
				"fieldtype": "Small Text",
				"label": "Rejection Remarks",
				"insert_after": closure_field,
				"allow_on_submit": 1,
			}
		)
	if fields:
		create_custom_fields({DOCTYPE: fields}, update=True)

	# remarks are entered while approving, which may be after submit
	if meta.is_submittable and meta.has_field(closure_field) and not meta.get_field(closure_field).allow_on_submit:
		make_property_setter(DOCTYPE, closure_field, "allow_on_submit", 1, "Check", validate_fields_for_doctype=False)
