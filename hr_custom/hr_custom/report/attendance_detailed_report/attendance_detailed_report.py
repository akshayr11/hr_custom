# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Attendance Detailed Report: per employee, the day code of each day of the month and the
totals, with the worked / extra hours and deduction minutes of the attendance.

Codes: P Present, L Late entry, E Early exit, LV Leave, R Rest day, A Absent, Ex Exception.
A day without attendance is Ex with an approved Attendance Request, LV with an approved leave,
R on a holiday / weekly off, and A when it is a past working day of the employee's service.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_last_day, getdate, today

from hr_custom.overrides.attendance import CODES
from hr_custom.utils import get_employee_payroll_details, get_matching_employees


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.month or not cint(filters.year):
		frappe.throw(_("Please set Month and Year"))

	start = getdate(f"{cint(filters.year)}-{list(calendar.month_name).index(filters.month):02d}-01")
	end = get_last_day(start)
	days = [add_days(start, i) for i in range((end - start).days + 1)]
	return get_columns(days), get_data(filters, start, end, days)


def get_columns(days):
	columns = [
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Data", "width": 120},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Data", "width": 120},
	]
	for day in days:
		columns.append(
			{
				"fieldname": f"d{day.day}",
				"label": f"{day.day:02d} {calendar.day_abbr[day.weekday()][:2]}",
				"fieldtype": "Data",
				"width": 52,
				"align": "center",
			}
		)
	for code, label in CODES.items():
		columns.append({"fieldname": f"total_{code.lower()}", "label": f"{code} ({_(label)})", "fieldtype": "Int", "width": 70})
	columns += [
		{"fieldname": "worked_hours", "label": _("Worked Hrs"), "fieldtype": "Float", "precision": 2, "width": 95},
		{"fieldname": "extra_hours", "label": _("Extra Hrs"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "deduction_minutes", "label": _("Deduction Min"), "fieldtype": "Int", "width": 105},
	]
	return columns


def get_data(filters, start, end, days):
	employees = get_employees(filters, start, end)
	if not employees:
		return []
	names = [e.name for e in employees]

	attendance = {}
	for d in frappe.get_all(
		"Attendance",
		filters={"employee": ("in", names), "docstatus": 1, "attendance_date": ("between", [start, end])},
		fields=["employee", "attendance_date", "attendance_code", "worked_minutes", "extra_minutes", "deduction_minutes"],
	):
		attendance[(d.employee, getdate(d.attendance_date))] = d

	leave_days = get_covered_days("Leave Application", names, start, end, {"status": "Approved"})
	request_days = get_covered_days("Attendance Request", names, start, end)
	cost_centers = get_employee_payroll_details(names)
	cost_center_names = dict(frappe.get_all("Cost Center", fields=["name", "cost_center_name"], as_list=True))
	holidays = HolidayDates(start, end)
	last_day = getdate(today())

	data = []
	for emp in employees:
		cost_center = (cost_centers.get(emp.name) or {}).get("payroll_cost_center")
		row = frappe._dict(
			employee=emp.name,
			employee_name=emp.employee_name,
			cost_center=cost_center_names.get(cost_center) or cost_center,
			designation=emp.designation,
			worked_hours=0.0,
			extra_hours=0.0,
			deduction_minutes=0,
			**{f"total_{code.lower()}": 0 for code in CODES},
		)
		rest_days = holidays.get(emp.name)
		for day in days:
			if (emp.date_of_joining and day < getdate(emp.date_of_joining)) or (
				emp.relieving_date and day > getdate(emp.relieving_date)
			):
				continue
			record = attendance.get((emp.name, day))
			if record:
				code = record.attendance_code
				row.worked_hours += flt(record.worked_minutes) / 60
				row.extra_hours += flt(record.extra_minutes) / 60
				row.deduction_minutes += cint(record.deduction_minutes)
			elif (emp.name, day) in request_days:
				code = "Ex"
			elif (emp.name, day) in leave_days:
				code = "LV"
			elif day in rest_days:
				code = "R"
			elif day <= last_day:
				code = "A"
			else:
				code = None
			if code:
				row[f"d{day.day}"] = code
				row[f"total_{code.lower()}"] += 1
		row.worked_hours = flt(row.worked_hours, 2)
		row.extra_hours = flt(row.extra_hours, 2)
		data.append(row)
	return data


def get_employees(filters, start, end):
	emp_filters = {"company": filters.company, "date_of_joining": ("<=", end)}
	if filters.employee:
		emp_filters["name"] = filters.employee
	employees = frappe.get_all(
		"Employee",
		filters=emp_filters,
		or_filters=[["relieving_date", "is", "not set"], ["relieving_date", ">=", start]],
		fields=["name", "employee_name", "designation", "date_of_joining", "relieving_date"],
		order_by="name",
	)
	if filters.payroll_cost_center:
		matching = get_matching_employees([e.name for e in employees], payroll_cost_center=filters.payroll_cost_center)
		employees = [e for e in employees if e.name in matching]
	return employees


def get_covered_days(doctype, employees, start, end, extra_filters=None):
	"""{(employee, date)} covered by the submitted documents' From - To dates."""
	days = set()
	for d in frappe.get_all(
		doctype,
		filters={
			"employee": ("in", employees),
			"docstatus": 1,
			"from_date": ("<=", end),
			"to_date": (">=", start),
			**(extra_filters or {}),
		},
		fields=["employee", "from_date", "to_date"],
	):
		day = max(getdate(d.from_date), start)
		while day <= min(getdate(d.to_date), end):
			days.add((d.employee, day))
			day = add_days(day, 1)
	return days


class HolidayDates:
	"""Holiday dates of the employee's holiday list in the month (cached per holiday list)."""

	def __init__(self, start, end):
		self.start, self.end, self.by_list = start, end, {}

	def get(self, employee):
		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

		holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
		if not holiday_list:
			return set()
		if holiday_list not in self.by_list:
			self.by_list[holiday_list] = {
				getdate(d)
				for d in frappe.get_all(
					"Holiday",
					filters={"parent": holiday_list, "holiday_date": ("between", [self.start, self.end])},
					pluck="holiday_date",
				)
			}
		return self.by_list[holiday_list]
