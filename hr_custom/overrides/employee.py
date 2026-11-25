"""Employee status from the Relieving Date: an employee with a Relieving Date is Inactive.

Removing the Relieving Date makes the employee Active again (only when it was this rule that made
them Inactive, i.e. the date was there before and the status is still Inactive). "Left" and
"Suspended" are left as they are.

Note: HRMS blocks Salary Slips, Additional Salary, Attendance, Leave Applications etc. for
Inactive employees and leaves them out of Payroll Entry.
"""

import frappe
from frappe import _


def set_status_from_relieving_date(doc, method=None):
	"""Employee validate."""
	if doc.relieving_date:
		if doc.status == "Active":
			doc.status = "Inactive"
			frappe.msgprint(
				_("Status set to Inactive as the Relieving Date is set"), indicator="orange", alert=True
			)
		return

	before = doc.get_doc_before_save()
	if before and before.relieving_date and doc.status == "Inactive" and before.status == "Inactive":
		doc.status = "Active"
		frappe.msgprint(_("Status set to Active as the Relieving Date is removed"), indicator="green", alert=True)
