# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee Rejoining: the date an employee actually came back from annual leave.

Approving it (workflow -> submit) sets the employee's Rejoin Date and adjusts the leave balance
against the annual Leave Application:

* Late: the days between the expected rejoin date (day after Leave To) and the actual one are
  taken as an approved Leave Application of "Deduct Late Days From" (annual leave by default,
  Leave Without Pay if the balance is short), so balance and attendance follow HRMS.
* Early: the leave days not taken are credited back to the leave allocation with a Leave Ledger
  Entry (as HRMS does for compensatory leave) and the "On Leave" attendance for them is cancelled.

Cancelling reverses both.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, formatdate, get_link_to_form, getdate

from hr_custom.overrides.rejoin_date import is_annual_leave, update_rejoin_date


class EmployeeRejoining(Document):
	def validate(self):
		self.validate_leave_application()
		self.validate_duplicate()
		self.set_rejoin_details()

	def validate_leave_application(self):
		leave = frappe.db.get_value(
			"Leave Application",
			self.leave_application,
			["employee", "docstatus", "status", "leave_type", "from_date"],
			as_dict=True,
		)
		if not leave:
			return
		if leave.employee != self.employee:
			frappe.throw(_("Leave Application {0} is not of employee {1}").format(self.leave_application, self.employee))
		if leave.docstatus != 1 or leave.status != "Approved":
			frappe.throw(_("Leave Application {0} is not approved and submitted").format(self.leave_application))
		if not is_annual_leave(leave.leave_type):
			frappe.throw(
				_("{0} is not an annual leave. Tick 'Rejoining Required' on the Leave Type if it needs rejoining.").format(
					frappe.bold(leave.leave_type)
				)
			)
		if self.rejoin_date and getdate(self.rejoin_date) <= getdate(leave.from_date):
			frappe.throw(_("Actual Rejoin Date must be after the leave starts ({0})").format(formatdate(leave.from_date)))

	def validate_duplicate(self):
		existing = frappe.db.get_value(
			"Employee Rejoining",
			{"leave_application": self.leave_application, "docstatus": ("<", 2), "name": ("!=", self.name)},
		)
		if existing:
			frappe.throw(
				_("Rejoining {0} is already made for this leave application").format(
					get_link_to_form("Employee Rejoining", existing)
				)
			)

	@frappe.whitelist()
	def set_rejoin_details(self):
		if not (self.leave_application and self.rejoin_date):
			return
		leave = frappe.db.get_value(
			"Leave Application", self.leave_application, ["leave_type", "from_date", "to_date", "total_leave_days"], as_dict=True
		)
		self.leave_type, self.leave_from_date, self.leave_to_date = leave.leave_type, leave.from_date, leave.to_date
		self.total_leave_days = leave.total_leave_days
		self.expected_rejoin_date = add_days(leave.to_date, 1)
		self.days_difference = date_diff(self.rejoin_date, self.expected_rejoin_date)

		if self.days_difference > 0:
			self.rejoin_status = "Late"
			self.extra_days_leave_type = self.extra_days_leave_type or self.leave_type
			self.leave_days_to_adjust = self.get_leave_days(
				self.extra_days_leave_type, self.expected_rejoin_date, add_days(self.rejoin_date, -1)
			)
		elif self.days_difference < 0:
			self.rejoin_status = "Early"
			self.extra_days_leave_type = None
			self.leave_days_to_adjust = self.get_leave_days(self.leave_type, self.rejoin_date, self.leave_to_date)
		else:
			self.rejoin_status = "On Time"
			self.extra_days_leave_type = None
			self.leave_days_to_adjust = 0

	def get_leave_days(self, leave_type, from_date, to_date):
		from hrms.hr.doctype.leave_application.leave_application import get_number_of_leave_days

		return get_number_of_leave_days(self.employee, leave_type, from_date, to_date)

	def on_submit(self):
		if self.rejoin_status == "Late" and self.leave_days_to_adjust:
			self.deduct_late_days()
		elif self.rejoin_status == "Early" and self.leave_days_to_adjust:
			self.credit_early_days()
		update_rejoin_date(self.employee)

	def on_cancel(self):
		if self.adjustment_leave_application:
			leave = frappe.get_doc("Leave Application", self.adjustment_leave_application)
			if leave.docstatus == 1:
				leave.flags.ignore_permissions = True
				leave.cancel()
		if self.leave_ledger_entry:
			frappe.db.delete("Leave Ledger Entry", {"name": self.leave_ledger_entry})
			# put back the "On Leave" attendance cancelled for the early days
			frappe.get_doc("Leave Application", self.leave_application).update_attendance()
		update_rejoin_date(self.employee)

	def deduct_late_days(self):
		# the approver of this rejoining approves the late days when the employee has no leave approver
		leave_approver = frappe.db.get_value("Employee", self.employee, "leave_approver") or frappe.session.user
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": self.extra_days_leave_type,
				"from_date": self.expected_rejoin_date,
				"to_date": add_days(self.rejoin_date, -1),
				"company": self.company,
				"posting_date": getdate(),
				"status": "Approved",
				"leave_approver": leave_approver,
				"follow_via_email": 0,
				"description": _("Late rejoining after {0} ({1})").format(self.leave_application, self.name),
			}
		)
		leave.flags.ignore_permissions = True
		leave.insert()
		leave.submit()
		self.db_set("adjustment_leave_application", leave.name)
		frappe.msgprint(
			_("{0} late day(s) taken as {1} in {2}").format(
				self.leave_days_to_adjust, self.extra_days_leave_type, get_link_to_form("Leave Application", leave.name)
			),
			alert=True,
		)

	def credit_early_days(self):
		allocation = frappe.db.get_value(
			"Leave Allocation",
			{
				"employee": self.employee,
				"leave_type": self.leave_type,
				"from_date": ("<=", self.rejoin_date),
				"to_date": (">=", self.rejoin_date),
				"docstatus": 1,
			},
			["name", "to_date"],
			as_dict=True,
		)
		if not allocation:
			frappe.throw(
				_("No {0} allocation found for {1} to credit the unused leave days").format(
					frappe.bold(self.leave_type), formatdate(self.rejoin_date)
				)
			)

		# counted in the balance like the allocation's own entries (HRMS does the same for compensatory leave)
		entry = frappe.get_doc(
			{
				"doctype": "Leave Ledger Entry",
				"employee": self.employee,
				"employee_name": self.employee_name,
				"leave_type": self.leave_type,
				"transaction_type": "Leave Allocation",
				"transaction_name": allocation.name,
				"leaves": self.leave_days_to_adjust,
				"from_date": self.rejoin_date,
				"to_date": allocation.to_date,
				"company": self.company,
				"is_carry_forward": 0,
				"is_expired": 0,
				"is_lwp": 0,
			}
		)
		entry.flags.ignore_permissions = True
		entry.submit()
		self.db_set({"leave_allocation": allocation.name, "leave_ledger_entry": entry.name})

		# the employee was at work on these days
		for name in frappe.get_all(
			"Attendance",
			{
				"employee": self.employee,
				"leave_application": self.leave_application,
				"attendance_date": ("between", [self.rejoin_date, self.leave_to_date]),
				"docstatus": 1,
			},
			pluck="name",
		):
			attendance = frappe.get_doc("Attendance", name)
			attendance.flags.ignore_permissions = True
			attendance.cancel()

		frappe.msgprint(
			_("{0} unused leave day(s) credited back to {1}").format(
				self.leave_days_to_adjust, get_link_to_form("Leave Allocation", allocation.name)
			),
			alert=True,
		)
