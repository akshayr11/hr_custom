"""Employee Rejoin Date.

Read-only date on the employee: the date of joining, then the day after the latest approved
annual leave (Leave Types ticked 'Rejoining Required'), or the actual date from its approved
Employee Rejoining.
"""

import frappe
from frappe.utils import add_days

LEAVE_TYPE_FIELD = "rejoining_required"


def is_annual_leave(leave_type):
	if not leave_type:
		return False
	if frappe.get_meta("Leave Type").has_field(LEAVE_TYPE_FIELD):
		return bool(frappe.db.get_value("Leave Type", leave_type, LEAVE_TYPE_FIELD))
	return "annual" in leave_type.lower()


def get_annual_leave_types():
	return [d for d in frappe.get_all("Leave Type", pluck="name") if is_annual_leave(d)]


def get_rejoin_date(employee):
	leave = frappe.db.get_value(
		"Leave Application",
		{
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"leave_type": ("in", get_annual_leave_types() or [""]),
		},
		["name", "to_date"],
		order_by="to_date desc",
		as_dict=True,
	)
	if not leave:
		return frappe.db.get_value("Employee", employee, "date_of_joining")

	rejoined = frappe.db.get_value("Employee Rejoining", {"leave_application": leave.name, "docstatus": 1}, "rejoin_date")
	return rejoined or add_days(leave.to_date, 1)


def update_rejoin_date(employee):
	frappe.db.set_value("Employee", employee, "rejoin_date", get_rejoin_date(employee))


def set_on_employee(doc, method=None):
	"""Employee validate: a new employee rejoins on the date of joining."""
	if doc.get("date_of_joining") and (not doc.get("rejoin_date") or doc.is_new()):
		doc.rejoin_date = doc.date_of_joining


def on_leave_application_change(doc, method=None):
	"""Leave Application on_submit / on_cancel."""
	if doc.status == "Approved" and is_annual_leave(doc.leave_type):
		update_rejoin_date(doc.employee)


def make_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "rejoin_date",
					"fieldtype": "Date",
					"label": "Rejoin Date",
					"insert_after": "date_of_joining",
					"read_only": 1,
					"no_copy": 1,
					"in_list_view": 1,
					"description": "Date of joining, then the day after the last annual leave (or the date in its Employee Rejoining)",
				}
			],
			"Leave Type": [
				{
					"fieldname": LEAVE_TYPE_FIELD,
					"fieldtype": "Check",
					"label": "Rejoining Required (Annual Leave)",
					"insert_after": "is_lwp",
					"description": "Sets the employee's Rejoin Date and allows an Employee Rejoining against these leaves",
				}
			],
		},
		update=True,
	)

	for leave_type in frappe.get_all("Leave Type", pluck="name"):
		if "annual" in leave_type.lower() and not frappe.db.get_value("Leave Type", leave_type, LEAVE_TYPE_FIELD):
			frappe.db.set_value("Leave Type", leave_type, LEAVE_TYPE_FIELD, 1)

	for employee in frappe.get_all("Employee", {"rejoin_date": ("is", "not set")}, pluck="name"):
		update_rejoin_date(employee)


@frappe.whitelist()
def get_rejoining_defaults(employee):
	"""Annual leave types, and the latest approved annual leave of the employee not rejoined yet."""
	leave_types = get_annual_leave_types()
	rejoined = frappe.get_all("Employee Rejoining", {"employee": employee, "docstatus": ("<", 2)}, pluck="leave_application")
	leave = frappe.db.get_value(
		"Leave Application",
		{
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"leave_type": ("in", leave_types or [""]),
			"name": ("not in", rejoined or [""]),
		},
		"name",
		order_by="to_date desc",
	)
	return {"leave_types": leave_types, "leave_application": leave}
