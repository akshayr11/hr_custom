"""Data for the 'Employee Payslip' print format of Salary Slip (fixed lines like the old payslip).

Salary components are put on the payslip lines with the same rules as the 'Payroll Additions and
Deductions' report (Payroll Report Settings mapping first, then the component name); fixed
allowances are split further into HRA / Food / Transport / ... by name.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from hr_custom.utils import EMPLOYEE_LOCATION_FIELD

EARNING_LINES = [
	"Basic",
	"HRA",
	"Food",
	"Transport",
	"Desert",
	"Living",
	"Special",
	"Other",
	"OT Amount",
	"AirFare",
	"Other Addition",
]
DEDUCTION_LINES = [
	"PASI",
	"Adv. Sal Ded",
	"Warning Ded",
	"Leave Ded",
	"Other Deduction",
	"Security Fund",
]

# fixed allowance -> payslip line, by words in the component name / abbreviation
ALLOWANCE_KEYWORDS = [
	("HRA", ("hra", "house", "housing", "accommodation")),
	("Food", ("food",)),
	("Transport", ("transport", "conveyance", "travel")),
	("Desert", ("desert",)),
	("Living", ("living", "cola")),
	("Special", ("special",)),
]

# report column (payroll_additions_and_deductions) -> payslip line
REPORT_COLUMN_LINES = {
	"Basic Salary": "Basic",
	"Airfare": "AirFare",
	"Overtime": "OT Amount",
	"Other Additions": "Other Addition",
	"Leave Salary": "Other Addition",
	"Increment": "Other Addition",
	"Claim Amount": "Other Addition",
	"PASI": "PASI",
	"Sec Fund": "Security Fund",
	"Installment": "Adv. Sal Ded",
	"Warning Deduction": "Warning Ded",
	"Leave Deduction": "Leave Ded",
	"Attendance Deduction": "Leave Ded",
	"Other Deductions": "Other Deduction",
}
# lines whose individual components are listed under 'Oth Addition / Oth Ded Details'
DETAIL_LINES = ("Other Addition", "Other Deduction")


def get_payslip_data(doc):
	from hr_custom.hr_custom.report.payroll_additions_and_deductions.payroll_additions_and_deductions import (
		get_classifier,
	)

	classify = get_classifier()
	abbrs = dict(frappe.get_all("Salary Component", fields=["name", "salary_component_abbr"], as_list=True))

	lines = {line: 0.0 for line in EARNING_LINES + DEDUCTION_LINES}
	details = {line: [] for line in DETAIL_LINES}
	basic_pay = allowances = 0.0

	for table in ("earnings", "deductions"):
		for d in doc.get(table) or []:
			if d.get("statistical_component") or d.get("do_not_include_in_total"):
				continue
			d.parentfield = table
			column = classify(d)
			if column == "Fixed Allowance":
				line = get_allowance_line(f"{d.salary_component} {abbrs.get(d.salary_component) or ''}")
			else:
				line = REPORT_COLUMN_LINES.get(column, "Other Addition" if table == "earnings" else "Other Deduction")

			lines[line] += flt(d.amount)
			if line in DETAIL_LINES:
				details[line].append((d.salary_component, flt(d.amount)))

			# contract salary (full month, before proration)
			if column == "Basic Salary":
				basic_pay += flt(d.default_amount or d.amount)
			elif column == "Fixed Allowance":
				allowances += flt(d.default_amount or d.amount)

	# loan installments are deducted outside the deductions table
	loan = flt(doc.get("total_loan_repayment"))
	if loan:
		lines["Adv. Sal Ded"] += loan

	return frappe._dict(
		employee=get_employee_details(doc.employee),
		attendance=get_attendance_summary(doc),
		earnings=[(_(line), lines[line]) for line in EARNING_LINES],
		deductions=[(_(line), lines[line]) for line in DEDUCTION_LINES],
		addition_details=details["Other Addition"],
		deduction_details=details["Other Deduction"],
		basic_pay=basic_pay,
		allowances=allowances,
		total_pay=basic_pay + allowances,
		status=_("Hold") if doc.get("status") == "Withheld" else _("Pay"),
		month=getdate(doc.start_date).strftime("%b-%Y"),
	)


def get_allowance_line(text):
	text = text.lower()
	for line, keywords in ALLOWANCE_KEYWORDS:
		if any(k in text for k in keywords):
			return line
	return "Other"


def get_employee_details(employee):
	meta = frappe.get_meta("Employee")
	location_field = EMPLOYEE_LOCATION_FIELD if meta.has_field(EMPLOYEE_LOCATION_FIELD) else "branch"
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["designation", "department", "bank_name", "bank_ac_no", location_field],
		as_dict=True,
	) or frappe._dict()
	emp.location = emp.get(location_field)
	return emp


def get_attendance_summary(doc):
	start, end = getdate(doc.start_date), getdate(doc.end_date)
	attendance = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"docstatus": 1,
			"attendance_date": ("between", [start, end]),
		},
		fields=["status", "leave_type"]
		+ (["actual_overtime_duration"] if frappe.get_meta("Attendance").has_field("actual_overtime_duration") else []),
	)

	annual = sick = overtime_seconds = 0.0
	for d in attendance:
		days = {"On Leave": 1, "Half Day": 0.5}.get(d.status, 0)
		leave_type = (d.leave_type or "").lower()
		if days and "annual" in leave_type:
			annual += days
		elif days and "sick" in leave_type:
			sick += days
		overtime_seconds += flt(d.get("actual_overtime_duration"))

	return frappe._dict(
		days_worked=flt(doc.payment_days),
		annual_leave=annual,
		sick_days=sick,
		unpaid=flt(doc.leave_without_pay),
		absent_days=flt(doc.get("absent_days")),
		ot_hours=flt(overtime_seconds / 3600, 2),
		rest_days=get_rest_days(doc.employee, start, end),
	)


def get_rest_days(employee, start, end):
	from hrms.hr.utils import get_holiday_dates_for_employee

	try:
		return len(get_holiday_dates_for_employee(employee, start, end))
	except Exception:
		# no holiday list for the employee / company
		frappe.clear_messages()
		return 0
