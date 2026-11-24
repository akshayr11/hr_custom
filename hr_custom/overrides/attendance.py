"""Attendance day code and attendance deduction minutes.

Each attendance gets a day code for the Attendance Detailed Report:
    P Present, L Late entry, E Early exit, LV Leave, R Rest day, A Absent, Ex Exception
(an approved Attendance Request). An absent day is LV when an approved leave covers it and R
when it is a holiday / weekly off in the employee's holiday list.

From the shift and the first-in / last-out of the day (in minutes):
    Org Duty   = Shift End - Shift Start
    Worked     = (Out - In) - Break Period
    Extra      = Worked - (Org Duty - Break Period)              (logged when > 0)
    In Diff    = In - (Shift Start + late entry grace period)
    Out Diff   = Out - Shift End
    Deduction  = 180 if there is an In but no Out
               + In Diff when > 0 + -Out Diff when < 0
The deduction minutes are approved (and the amount worked out) in Attendance Deduction.
"""

from datetime import datetime, timedelta

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, get_datetime, get_time, getdate

MISSING_OUT_MINUTES = 180
CODES = {
	"P": "Present",
	"L": "Late Entry",
	"E": "Early Exit",
	"LV": "Leave",
	"R": "Rest Day",
	"A": "Absent",
	"Ex": "Exception",
}
MINUTE_FIELDS = (
	"org_duty_minutes",
	"worked_minutes",
	"extra_minutes",
	"in_diff_minutes",
	"out_diff_minutes",
	"deduction_minutes",
)


def validate(doc, method=None):
	"""Attendance validate (also when HRMS marks it from check-ins, leave or attendance request)."""
	doc.attendance_code = get_attendance_code(doc)
	doc.update(get_deduction_minutes(doc))


def get_attendance_code(doc):
	if doc.get("attendance_request"):
		return "Ex"
	if doc.status == "On Leave":
		return "LV"
	if doc.status == "Rest Day":  # status added by oerp_overtime
		return "R"
	if doc.status == "Absent":
		if has_approved_leave(doc.employee, doc.attendance_date):
			return "LV"
		if is_rest_day(doc.employee, doc.attendance_date):
			return "R"
		return "A"
	if cint(doc.get("late_entry")):
		return "L"
	if cint(doc.get("early_exit")):
		return "E"
	return "P"


def has_approved_leave(employee, date):
	return bool(
		frappe.db.exists(
			"Leave Application",
			{
				"employee": employee,
				"docstatus": 1,
				"status": "Approved",
				"from_date": ("<=", date),
				"to_date": (">=", date),
			},
		)
	)


def is_rest_day(employee, date):
	from erpnext.setup.doctype.employee.employee import is_holiday

	return bool(is_holiday(employee, date, raise_exception=False))


def get_deduction_minutes(doc):
	minutes = dict.fromkeys(MINUTE_FIELDS, 0)
	# an exception (approved attendance request) or leave day is not deducted
	if (
		not (doc.get("shift") and doc.get("in_time"))
		or doc.get("attendance_request")
		or doc.status in ("On Leave", "Rest Day")
	):
		return minutes

	shift = frappe.get_cached_value(
		"Shift Type", doc.shift, ["start_time", "end_time", "late_entry_grace_period", "break_period"], as_dict=True
	)
	if not shift:
		return minutes
	return calculate_minutes(doc.attendance_date, shift, doc.in_time, doc.out_time)


def calculate_minutes(attendance_date, shift, in_time, out_time):
	start = datetime.combine(getdate(attendance_date), get_time(shift.start_time))
	end = datetime.combine(getdate(attendance_date), get_time(shift.end_time))
	if end <= start:  # night shift ends the next day
		end += timedelta(days=1)
	break_period = cint(shift.get("break_period"))
	in_time = get_datetime(in_time)
	# a single punch is an In without an Out
	out_time = get_datetime(out_time) if out_time and get_datetime(out_time) != in_time else None

	org_duty = diff_minutes(start, end)
	in_diff = diff_minutes(start + timedelta(minutes=cint(shift.get("late_entry_grace_period"))), in_time)
	minutes = {
		"org_duty_minutes": org_duty,
		"in_diff_minutes": in_diff,
		"worked_minutes": 0,
		"extra_minutes": 0,
		"out_diff_minutes": 0,
	}
	if out_time:
		worked = diff_minutes(in_time, out_time) - break_period
		minutes.update(
			worked_minutes=worked,
			extra_minutes=max(worked - (org_duty - break_period), 0),
			out_diff_minutes=diff_minutes(end, out_time),
		)

	minutes["deduction_minutes"] = (
		(0 if out_time else MISSING_OUT_MINUTES)
		+ max(minutes["in_diff_minutes"], 0)
		+ max(-minutes["out_diff_minutes"], 0)
	)
	return minutes


def diff_minutes(start, end):
	return round((end - start).total_seconds() / 60)


def refresh_attendance(employee, from_date, to_date):
	"""Leave / Attendance Request change HRMS attendance with db_set (no validate): redo the code
	and minutes of the employee's attendance in the period."""
	for name in frappe.get_all(
		"Attendance",
		{"employee": employee, "attendance_date": ("between", [from_date, to_date]), "docstatus": ("<", 2)},
		pluck="name",
	):
		doc = frappe.get_doc("Attendance", name)
		values = {"attendance_code": get_attendance_code(doc), **get_deduction_minutes(doc)}
		if any(doc.get(field) != value for field, value in values.items()):
			doc.db_set(values, update_modified=False)


def on_leave_or_request_change(doc, method=None):
	"""Leave Application / Attendance Request on_submit / on_cancel."""
	refresh_attendance(doc.employee, doc.from_date, doc.to_date)


def make_fields():
	options = "\n" + "\n".join(CODES)
	description = ", ".join(f"{code} = {label}" for code, label in CODES.items())

	def minutes(fieldname, label, insert_after, **kw):
		return {
			"fieldname": fieldname,
			"fieldtype": "Int",
			"label": label,
			"insert_after": insert_after,
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			**kw,
		}

	create_custom_fields(
		{
			"Attendance": [
				{
					"fieldname": "attendance_code",
					"fieldtype": "Select",
					"label": "Attendance Code",
					"options": options,
					"insert_after": "status",
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": description,
				},
				{
					"fieldname": "attendance_deduction_section",
					"fieldtype": "Section Break",
					"label": "Attendance Deduction (minutes)",
					"insert_after": "out_time",
					"collapsible": 1,
				},
				minutes("org_duty_minutes", "Org Duty", "attendance_deduction_section"),
				minutes("worked_minutes", "Worked", "org_duty_minutes"),
				minutes("extra_minutes", "Extra", "worked_minutes"),
				{"fieldname": "attendance_deduction_column", "fieldtype": "Column Break", "insert_after": "extra_minutes"},
				minutes("in_diff_minutes", "In Diff", "attendance_deduction_column", description="+ late, - early"),
				minutes("out_diff_minutes", "Out Diff", "in_diff_minutes", description="- early exit, + stayed late"),
				minutes(
					"deduction_minutes",
					"Deduction",
					"out_diff_minutes",
					bold=1,
					description=f"{MISSING_OUT_MINUTES} if no check-out + late minutes + early exit minutes",
				),
			],
			"Shift Type": [
				{
					"fieldname": "break_period",
					"fieldtype": "Int",
					"label": "Break Period (Minutes)",
					"insert_after": "end_time",
					"non_negative": 1,
					"description": "Taken off the worked time of the attendance deduction",
				}
			],
		},
		update=True,
	)
