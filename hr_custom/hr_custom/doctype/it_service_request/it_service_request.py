# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from hr_custom.utils import EMPLOYEE_LOCATION_FIELD

IT_ADMIN = "IT Admin"

# (from, to) -> who may make the change: the requester or the IT Admin.
# Draft -> Pending -> Submitted happens before submit; the rest after.
TRANSITIONS = {
	("Draft", "Pending for Submission"): "requester",
	("Pending for Submission", "Draft"): "requester",
	("Submitted", "Received"): "it_admin",
	("Received", "In Progress"): "it_admin",
	("Reopened", "In Progress"): "it_admin",
	("In Progress", "Completed"): "it_admin",
	("Completed", "Closed"): "requester",
	("Completed", "Reopened"): "requester",
}

# fields the requester fills; locked while Pending for Submission
REQUEST_FIELDS = (
	"employee",
	"request_type",
	"request_date",
	"contact_no",
	"email",
	"system_type",
	"system_code",
	"brand_model",
	"problem_type",
	"erp_module",
	"description",
)


class ITServiceRequest(Document):
	def validate(self):
		self.set_location()
		self.validate_request_details()
		if self.docstatus == 0:
			self.validate_draft_status()

	def before_submit(self):
		if self.status != "Pending for Submission":
			frappe.throw(_("Click 'Send for Submission' first, then Submit"))
		self.status = "Submitted"

	def before_update_after_submit(self):
		self.validate_status_change()
		self.set_it_dates()

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def validate_draft_status(self):
		if self.status not in ("Draft", "Pending for Submission"):
			self.status = "Draft"

		before = self.get_doc_before_save()
		if not before:
			return
		if before.status != self.status:
			validate_transition(self, before.status, self.status)
		elif self.status == "Pending for Submission":
			changed = [self.meta.get_label(f) for f in REQUEST_FIELDS if before.get(f) != self.get(f)]
			if changed:
				frappe.throw(
					_("This request is Pending for Submission. Click 'Back to Draft' to edit {0}.").format(
						", ".join(changed)
					)
				)

	def validate_status_change(self):
		before = self.get_doc_before_save()
		if before and before.status != self.status:
			validate_transition(self, before.status, self.status)

	def validate_request_details(self):
		# rules come from the IT Request Type master; mandatory_depends_on is only enforced in the browser
		flags = (
			frappe.get_cached_value(
				"IT Request Type",
				self.request_type,
				["requires_system_details", "requires_erp_module"],
				as_dict=True,
			)
			or {}
		)
		self.requires_system_details = flags.get("requires_system_details") or 0
		self.requires_erp_module = flags.get("requires_erp_module") or 0

		if self.requires_erp_module:
			if not self.erp_module:
				frappe.throw(
					_("Please select the ERP Module (required for Request Type {0})").format(self.request_type),
					frappe.MandatoryError,
				)
		else:
			self.erp_module = None

		if self.requires_system_details:
			missing = [self.meta.get_label(f) for f in ("system_type", "system_code") if not self.get(f)]
			if missing:
				frappe.throw(
					_("Please enter {0} (required for Request Type {1})").format(
						", ".join(missing), self.request_type
					),
					frappe.MandatoryError,
				)

	def set_location(self):
		"""Employee Location if the site has it, else Branch."""
		if not self.employee:
			return
		meta = frappe.get_meta("Employee")
		fieldname = EMPLOYEE_LOCATION_FIELD if meta.has_field(EMPLOYEE_LOCATION_FIELD) else "branch"
		self.location = frappe.db.get_value("Employee", self.employee, fieldname)

	def set_it_dates(self):
		if self.status == "Received" and not self.date_received:
			self.date_received = today()
		if self.status == "Completed":
			self.action_date = today()

	def is_requester(self, user=None):
		user = user or frappe.session.user
		return user in (self.owner, frappe.db.get_value("Employee", self.employee, "user_id"))


def is_it_admin(user=None):
	roles = frappe.get_roles(user or frappe.session.user)
	return IT_ADMIN in roles or "System Manager" in roles


def validate_transition(doc, old, new):
	who = TRANSITIONS.get((old, new))
	if not who:
		frappe.throw(_("Status cannot be changed from {0} to {1}").format(_(old), _(new)))

	if "System Manager" in frappe.get_roles():
		return
	if who == "requester" and not doc.is_requester():
		frappe.throw(_("Only the requester can change the status from {0} to {1}").format(_(old), _(new)))
	if who == "it_admin" and not is_it_admin():
		frappe.throw(_("Only {0} can change the status to {1}").format(IT_ADMIN, _(new)))


def get_allowed_statuses(doc):
	"""Statuses the current user can move this request to."""
	allowed = []
	for (old, new), who in TRANSITIONS.items():
		if old != doc.status:
			continue
		if (who == "requester" and doc.is_requester()) or (who == "it_admin" and is_it_admin()):
			allowed.append(new)
		elif "System Manager" in frappe.get_roles():
			allowed.append(new)
	return allowed


@frappe.whitelist()
def get_status_actions(name):
	doc = frappe.get_doc("IT Service Request", name)
	doc.check_permission("read")
	return get_allowed_statuses(doc)


@frappe.whitelist()
def change_status(name, status, reason=None):
	"""Move the request along the workflow. Permission comes from the transition rules (the requester
	may Close/Reopen without write access to Status)."""
	doc = frappe.get_doc("IT Service Request", name)
	doc.check_permission("read")
	validate_transition(doc, doc.status, status)

	doc.status = status
	doc.save(ignore_permissions=True)

	if reason:
		doc.add_comment("Comment", _("{0}: {1}").format(_(status), reason))
	return doc.status


@frappe.whitelist()
def get_employee_for_user():
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
