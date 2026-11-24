"""Leave Application fixes on top of oerp_earned_leaves' CustomLeaveApplication.

That class only runs HRMS's validate, on_submit and on_cancel for its annual leave types, so any
other leave (e.g. Sick Leave) was submitted without validation, leave ledger entry or attendance,
and its cancel did nothing. Its annual balance check also compares with total_leave_days before
it is worked out, which fails for leaves made in code (Employee Rejoining's late days):
TypeError: '<' not supported between instances of 'float' and 'NoneType'.

The mixin sits before that class: other leave types run HRMS as is, annual leaves keep the
oerp_earned_leaves logic with the leave days set first. Without oerp_earned_leaves it is HRMS.
"""

import frappe
from frappe import _
from hrms.hr.doctype.leave_application.leave_application import LeaveApplication, get_number_of_leave_days

# the leave types oerp_earned_leaves handles itself
EARNED_LEAVE_TYPES = ("Annual Leave", "Annual Leave 30", "Annual Leave 60")


class LeaveApplicationMixin:
	def is_earned_leave(self):
		return self.leave_type in EARNED_LEAVE_TYPES

	def validate(self):
		if self.is_earned_leave():
			return super().validate()
		return LeaveApplication.validate(self)

	def validate_balance_leaves(self):
		if not self.is_earned_leave():
			return LeaveApplication.validate_balance_leaves(self)

		if self.from_date and self.to_date:
			self.total_leave_days = get_number_of_leave_days(
				self.employee, self.leave_type, self.from_date, self.to_date, self.half_day, self.half_day_date
			)
			if self.total_leave_days <= 0:
				frappe.throw(
					_("The day(s) on which you are applying for leave are holidays. You need not apply for leave.")
				)
		return super().validate_balance_leaves()

	def on_submit(self):
		if self.is_earned_leave():
			return super().on_submit()
		return LeaveApplication.on_submit(self)

	def on_cancel(self):
		if self.is_earned_leave():
			return super().on_cancel()
		return LeaveApplication.on_cancel(self)
