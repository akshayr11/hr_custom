"""Transport documents (oerp_custom): save who performed each workflow step, like Material Request's
Prepared / Approved By.

When the workflow state changes, the full name of the session user is written to the field for the
step the action was taken in (e.g. 'Approve' in 'Site Manager Approval' -> Site Manager Approved By).
A move to 'Rejected' fills Rejected By instead.
"""

import frappe

PREPARED = ("prepared_by", "Prepared By")
TRANSPORT_OFFICER = ("transport_officer_approved_by", "Transport Officer Approved By")
CONTRACT_MANAGER = ("contract_manager_approved_by", "Contract Manager Approved By")
REJECTED = ("rejected_by", "Rejected By")

# doctype -> {workflow state the action is taken in: (fieldname, label)}
WORKFLOW_USER_FIELDS = {
	"Fleet Hiring Request": {
		"Draft": PREPARED,
		"Site Manager Approval": ("site_manager_approved_by", "Site Manager Approved By"),
		"Contract Manager Approval": CONTRACT_MANAGER,
		"Transport Officer Final Approval": TRANSPORT_OFFICER,
	},
	"Hiring Contract": {
		"Draft": PREPARED,
		"Contract Manager Approval": CONTRACT_MANAGER,
	},
	"Equipment Timesheet": {
		"Draft": PREPARED,
		"Transport Officer Final Approval": TRANSPORT_OFFICER,
	},
	"Hiring Receipt": {
		"Draft": PREPARED,
		"Transport Officer Final Approval": TRANSPORT_OFFICER,
	},
}


def set_workflow_users(doc, method=None):
	"""validate hook: record the user who moved the document to its new workflow state."""
	steps = WORKFLOW_USER_FIELDS.get(doc.doctype)
	state_field = get_state_field(doc.doctype)
	if not steps or not state_field:
		return

	before = doc.get_doc_before_save()
	old_state = before.get(state_field) if before else None
	new_state = doc.get(state_field)
	if not old_state or old_state == new_state:
		return

	if "reject" in (new_state or "").lower():
		fieldname = REJECTED[0]
	else:
		fieldname = (steps.get(old_state) or (None,))[0]

	if fieldname and doc.meta.has_field(fieldname):
		doc.set(fieldname, get_full_name())


def get_state_field(doctype):
	from frappe.model.workflow import get_workflow_name, get_workflow_state_field

	workflow = get_workflow_name(doctype)
	return get_workflow_state_field(workflow) if workflow else None


def get_full_name(user=None):
	user = user or frappe.session.user
	return frappe.db.get_value("User", user, "full_name") or user


def make_fields():
	"""Read-only 'Approval Details' section at the end of each transport form."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	custom_fields = {}
	for doctype, steps in WORKFLOW_USER_FIELDS.items():
		if not frappe.db.exists("DocType", doctype):
			continue

		meta = frappe.get_meta(doctype)
		fields = []
		previous = meta.fields[-1].fieldname if meta.fields else None
		fields.append(
			{
				"fieldname": "approval_details_section",
				"fieldtype": "Section Break",
				"label": "Approval Details",
				"insert_after": previous,
				"collapsible": 0,
			}
		)
		previous = "approval_details_section"

		ordered = []
		for field in [*steps.values(), REJECTED]:
			if field not in ordered:
				ordered.append(field)

		for i, (fieldname, label) in enumerate(ordered):
			if i and i % 2 == 0:
				# two per row
				fields.append(
					{
						"fieldname": f"approval_details_break_{i}",
						"fieldtype": "Section Break",
						"insert_after": previous,
					}
				)
				previous = f"approval_details_break_{i}"
			elif i % 2 == 1:
				fields.append(
					{
						"fieldname": f"approval_details_column_{i}",
						"fieldtype": "Column Break",
						"insert_after": previous,
					}
				)
				previous = f"approval_details_column_{i}"

			fields.append(
				{
					"fieldname": fieldname,
					"fieldtype": "Data",
					"label": label,
					"insert_after": previous,
					"read_only": 1,
					"no_copy": 1,
					"allow_on_submit": 1,
				}
			)
			previous = fieldname

		custom_fields[doctype] = fields

	if custom_fields:
		create_custom_fields(custom_fields, update=True)
