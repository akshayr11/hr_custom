# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee Attendance Details: one row per employee per day with the shift, the check-in and
check-out times, early / late check-in and check-out minutes, worked and extra time, the
deduction minutes and the day code (P, L, E, LV, R, A, Ex - see Attendance Detailed Report),
with a total row per employee.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, cint, get_datetime, get_time, getdate, today

from hr_custom.hr_custom.report.attendance_detailed_report.attendance_detailed_report import (
	HolidayDates,
	get_covered_days,
	get_employees,
)
from hr_custom.hr_custom.report.gratuity_details.gratuity_details import ID_FIELDS
from hr_custom.overrides.attendance import CODES
from hr_custom.utils import (
	get_employee_category,
	get_employee_payroll_details,
	get_nationality_field,
	has_employee_category,
)

MINUTE_COLUMNS = ("early_in", "late_in", "early_out", "late_out", "extra_minutes", "deduction_minutes")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.from_date and filters.to_date):
		frappe.throw(_("Please set From Date and To Date"))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if start > end:
		frappe.throw(_("From Date cannot be after To Date"))
	if (end - start).days > 92:
		frappe.throw(_("Please select a period of at most 3 months"))
	return get_columns(), get_data(filters, start, end)


def get_columns():
	def minutes(fieldname, label, width=85):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Int", "width": width}

	def text(fieldname, label, width=75):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Data", "width": width}

	return [
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 110},
		text("employee_name", _("Name"), 150),
		text("department", _("Department"), 120),
		text("designation", _("Designation"), 120),
		text("nationality", _("Nationality"), 90),
		text("employee_category", _("Omani / Expat"), 80),
		text("civil_id", _("Civil ID"), 100),
		{"fieldname": "date_of_joining", "label": _("Joining Date"), "fieldtype": "Date", "width": 95},
		text("employment_type", _("Employment Type"), 100),
		text("cost_center", _("Cost Center"), 110),
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		text("day", _("Day"), 50),
		{"fieldname": "shift", "label": _("Shift"), "fieldtype": "Link", "options": "Shift Type", "width": 100},
		text("shift_start", _("Shift In")),
		text("shift_end", _("Shift Out")),
		text("check_in", _("Check-in")),
		text("check_out", _("Check-out")),
		{"fieldname": "punches", "label": _("Punches"), "fieldtype": "Int", "width": 70},
		minutes("early_in", _("Early In (Min)")),
		minutes("late_in", _("Late In (Min)")),
		minutes("early_out", _("Early Out (Min)")),
		minutes("late_out", _("Late Out (Min)")),
		text("worked", _("Worked (H:MM)"), 95),
		minutes("extra_minutes", _("Extra (Min)")),
		minutes("deduction_minutes", _("Deduction (Min)"), 100),
		text("code", _("Code"), 55),
		text("status", _("Status"), 90),
		text("remarks", _("Remarks"), 220),
	]


def get_data(filters, start, end):
	employees = get_employees(filters, start, end)
	if not employees:
		return []
	names = [e.name for e in employees]

	attendance = {
		(d.employee, getdate(d.attendance_date)): d
		for d in frappe.get_all(
			"Attendance",
			filters={"employee": ("in", names), "docstatus": 1, "attendance_date": ("between", [start, end])},
			fields=[
				"name",
				"employee",
				"attendance_date",
				"status",
				"attendance_code",
				"shift",
				"in_time",
				"out_time",
				"late_entry",
				"early_exit",
				"leave_type",
				"attendance_request",
				"worked_minutes",
				"in_diff_minutes",
				"out_diff_minutes",
				"extra_minutes",
				"deduction_minutes",
			],
		)
	}
	checkin = frappe.qb.DocType("Employee Checkin")
	punches = dict(
		frappe.qb.from_(checkin)
		.select(checkin.attendance, Count(checkin.name))
		.where(checkin.attendance.isin([d.name for d in attendance.values()] or [""]))
		.groupby(checkin.attendance)
		.run()
	)
	leaves = get_covered_days("Leave Application", names, start, end, {"status": "Approved"}, label_field="leave_type")
	requests = get_covered_days("Attendance Request", names, start, end, label_field="reason")
	shifts = {
		d.name: d for d in frappe.get_all("Shift Type", fields=["name", "start_time", "end_time", "late_entry_grace_period"])
	}
	cost_centers = get_employee_payroll_details(names)
	cost_center_names = dict(frappe.get_all("Cost Center", fields=["name", "cost_center_name"], as_list=True))
	details = get_employee_details(names)
	holidays = HolidayDates(start, end)
	last_day = getdate(today())

	data = []
	for emp in employees:
		cost_center = (cost_centers.get(emp.name) or {}).get("payroll_cost_center")
		common = {
			"employee": emp.name,
			"employee_name": emp.employee_name,
			**details.get(emp.name, {}),
			"cost_center": cost_center_names.get(cost_center) or cost_center,
		}
		rest_days = holidays.get(emp.name)
		rows = []
		day = start
		while day <= end:
			if (emp.date_of_joining and day < getdate(emp.date_of_joining)) or (
				emp.relieving_date and day > getdate(emp.relieving_date)
			):
				day = add_days(day, 1)
				continue
			row = frappe._dict(common, date=day, day=_(day.strftime("%a")))
			record = attendance.get((emp.name, day))
			if record:
				set_attendance_details(row, record, shifts.get(record.shift), punches.get(record.name, 0))
			elif (emp.name, day) in requests:
				row.update(code="Ex", remarks=_("Attendance Request: {0}").format(_(requests[(emp.name, day)] or "")))
			elif (emp.name, day) in leaves:
				row.update(code="LV", remarks=leaves[(emp.name, day)])
			elif day in rest_days:
				row.update(code="R", remarks=rest_days[day] or _("Holiday"))
			elif day <= last_day:
				row.update(code="A", remarks=_("No attendance"))
			if row.code:
				row.status = _(CODES[row.code])
			if not filters.code or row.code == filters.code:
				rows.append(row)
			day = add_days(day, 1)

		if rows:
			data += rows
			data.append(get_total_row(common, rows))
			data.append({})
	return data[:-1]


def get_employee_details(employees):
	"""{employee: department, designation, nationality, employee_category, civil_id, date_of_joining,
	employment_type} - Civil ID and nationality from the site's own fields when it has them."""
	meta = frappe.get_meta("Employee")
	nationality = get_nationality_field()
	civil_id = next((f for f in ID_FIELDS if meta.has_field(f)), None)
	fields = ["name", "department", "designation", "date_of_joining", "employment_type"]
	fields += [f"{f} as {alias}" for f, alias in ((nationality, "nationality"), (civil_id, "civil_id")) if f]
	if has_employee_category():
		fields.append("employee_category")

	details = {}
	for d in frappe.get_all("Employee", filters={"name": ("in", employees)}, fields=fields):
		d.employee_category = d.get("employee_category") or get_employee_category(d.get("nationality"))
		details[d.pop("name")] = d
	return details


def set_attendance_details(row, record, shift, punches):
	row.update(code=record.attendance_code, shift=record.shift, punches=punches)
	remarks = []
	if shift:
		row.shift_start = format_time(shift.start_time)
		row.shift_end = format_time(shift.end_time)
	if record.in_time:
		in_time = get_datetime(record.in_time)
		row.check_in = format_clock(in_time, row.date)
		if shift:
			shift_start = datetime.combine(row.date, get_time(shift.start_time))
			row.early_in = max(round((shift_start - in_time).total_seconds() / 60), 0)
		row.late_in = max(cint(record.in_diff_minutes), 0)
	out_time = get_datetime(record.out_time) if record.out_time else None
	if out_time and out_time != get_datetime(record.in_time):
		row.check_out = format_clock(out_time, row.date)
		row.early_out = max(-cint(record.out_diff_minutes), 0)
		row.late_out = max(cint(record.out_diff_minutes), 0)
	elif record.in_time and record.status != "On Leave":
		remarks.append(_("No check-out"))

	row.worked_minutes = cint(record.worked_minutes)
	row.worked = format_minutes(row.worked_minutes) if row.worked_minutes else None
	row.extra_minutes = cint(record.extra_minutes)
	row.deduction_minutes = cint(record.deduction_minutes)

	if record.late_entry:
		remarks.append(_("Late Entry"))
	if record.early_exit:
		remarks.append(_("Early Exit"))
	if record.leave_type:
		remarks.append(record.leave_type)
	if record.attendance_request:
		remarks.append(_("Attendance Request {0}").format(record.attendance_request))
	if record.status in ("Absent", "Half Day") and not record.in_time:
		remarks.append(_(record.status))
	row.remarks = ", ".join(remarks)


def get_total_row(common, rows):
	total = frappe._dict(common, day=_("Total"), bold=1, punches=sum(cint(r.punches) for r in rows))
	for field in MINUTE_COLUMNS:
		total[field] = sum(cint(r.get(field)) for r in rows)
	worked = sum(cint(r.get("worked_minutes")) for r in rows)
	total.worked = format_minutes(worked) if worked else None
	counts = {code: sum(1 for r in rows if r.code == code) for code in CODES}
	total.remarks = ", ".join(f"{code} {count}" for code, count in counts.items() if count)
	return total


def format_time(value):
	return get_time(value).strftime("%H:%M") if value not in (None, "") else None


def format_clock(value, date):
	"""HH:MM, with (+1) for a punch on the next day (night shift)."""
	text = value.strftime("%H:%M")
	return f"{text} (+{(value.date() - date).days})" if value.date() > date else text


def format_minutes(minutes):
	sign = "-" if minutes < 0 else ""
	minutes = abs(minutes)
	return f"{sign}{minutes // 60}:{minutes % 60:02d}"
