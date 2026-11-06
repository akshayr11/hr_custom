# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""ICV Workforce Report: per employee and payroll cost center, the hours worked and the
compensation in USD for the payroll months From - To.

* Gross Salary: monthly earnings of the salary structure (full month, without Additional Salary
  such as OT) - averaged over the months; Gross Sal USD at the USD exchange rate.
* Head Office cost centers (Is Head Office) work 8 hours a day over 22 days, the others 12 hours
  over 30 days: Compensation Per Hour = Gross Sal USD / (days * hours).
* Total Hours Worked = payment days * daily hours + OT hours (attendance overtime);
  Total Compensation USD = Compensation Per Hour * Total Hours Worked.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, getdate

from hr_custom.hr_custom.report.job_category_salary_detail.job_category_salary_detail import get_full_month_gross
from hr_custom.hr_custom.report.payroll_additions_and_deductions.payroll_additions_and_deductions import (
	get_classifier,
	get_salary_details,
)
from hr_custom.utils import (
	EMPLOYEE_CATEGORIES,
	get_employee_category,
	get_nationality_field,
	has_employee_category,
	salary_slip_cost_center,
)

# same for every employee in the print
CONSTANTS = {
	"sourced_by": "Contractor",
	"jsrs_registering": "Yes",
	"jsrs_cr_no": "OM100751",
	"vendor_category": "NRS",
	"work_type": "Full-Time",
}
# (daily hours, days a month) used for the hourly compensation
HEAD_OFFICE_HOURS, HEAD_OFFICE_DAYS = 8, 22
SITE_HOURS, SITE_DAYS = 12, 30
MONTH_DAYS = 30
# Omani Rial is pegged to the US Dollar; used when no Currency Exchange record is found
OMR_TO_USD = 2.6008
ID_FIELDS = ("custom_civil_id", "civil_id", "custom_id_no", "id_no", "custom_civil_id_no", "national_id")
NO_VALUE_TYPES = ("Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Table MultiSelect", "Fold", "Heading")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = get_period(filters)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")
	usd_rate = flt(filters.usd_rate) or get_usd_rate(currency, to_date)
	if not usd_rate:
		frappe.throw(_("No exchange rate from {0} to USD found. Please set USD Exchange Rate.").format(currency))

	data = get_data(filters, from_date, to_date, currency, usd_rate)
	message = _("1 {0} = {1} USD").format(currency, usd_rate)
	return get_columns(), data, message


def get_period(filters):
	if not (filters.from_month and cint(filters.from_year) and filters.to_month and cint(filters.to_year)):
		frappe.throw(_("Please set From and To Month and Year"))
	from_date = getdate(f"{cint(filters.from_year)}-{list(calendar.month_name).index(filters.from_month):02d}-01")
	to_date = get_last_day(f"{cint(filters.to_year)}-{list(calendar.month_name).index(filters.to_month):02d}-01")
	if from_date > to_date:
		frappe.throw(_("From Month cannot be after To Month"))
	return from_date, to_date


def get_usd_rate(currency, date):
	from erpnext.setup.utils import get_exchange_rate

	rate = flt(get_exchange_rate(currency, "USD", date))
	return rate or (OMR_TO_USD if currency == "OMR" else 0)


def get_columns():
	def money(fieldname, label, options="currency", width=120):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "options": options, "width": width}

	def number(fieldname, label, width=110):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Float", "precision": 2, "width": width}

	return [
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "civil_id", "label": _("Civil ID"), "fieldtype": "Data", "width": 110},
		{"fieldname": "cost_center", "label": _("Cost Center"), "fieldtype": "Data", "width": 150},
		{"fieldname": "nationality", "label": _("Nationality"), "fieldtype": "Data", "width": 100},
		{"fieldname": "qualification", "label": _("Qualification"), "fieldtype": "Data", "width": 130},
		{"fieldname": "icv_job_category", "label": _("ICV Job Category"), "fieldtype": "Data", "width": 140},
		{"fieldname": "icv_designation", "label": _("ICV Designation"), "fieldtype": "Data", "width": 140},
		money("gross_salary", _("Gross Salary")),
		money("gross_salary_usd", _("Gross Sal USD"), "usd"),
		{"fieldname": "daily_hours", "label": _("Emp Working Hours"), "fieldtype": "Int", "width": 90},
		{"fieldname": "monthly_hours", "label": _("Monthly Working Hours"), "fieldtype": "Int", "width": 100},
		number("total_working_hours", _("Total Working Hours")),
		{
			"fieldname": "compensation_per_hour",
			"label": _("Compensation Per Hour (USD)"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		number("ot_hours", _("OT Hours"), 90),
		money("ot_amount", _("OT Amount")),
		number("total_hours_worked", _("Total Hours Worked")),
		money("total_compensation_usd", _("Total Compensation USD"), "usd", 140),
		{"fieldname": "employee_category", "label": _("Omani / Expat"), "fieldtype": "Data", "width": 90},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
		{"fieldname": "usd", "label": _("USD"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters, from_date, to_date, currency, usd_rate):
	slips = get_salary_slips(filters, from_date, to_date)
	if filters.employee_category in EMPLOYEE_CATEGORIES:
		slips = [s for s in slips if get_category(s) == filters.employee_category]
	if not slips:
		return []

	classify = get_classifier()
	details = get_salary_details([s.salary_slip for s in slips])
	gross = get_full_month_gross([s.salary_slip for s in slips])
	overtime = get_overtime_hours(slips)
	employees = get_employee_details({s.employee for s in slips})
	cost_centers = {
		d.name: d
		for d in frappe.get_all(
			"Cost Center",
			fields=["name", "cost_center_name"]
			+ (["is_head_office"] if frappe.get_meta("Cost Center").has_field("is_head_office") else []),
		)
	}

	rows = {}
	for slip in slips:
		row = rows.get((slip.employee, slip.cost_center))
		if not row:
			cost_center = cost_centers.get(slip.cost_center) or frappe._dict(cost_center_name=slip.cost_center)
			daily_hours, days = (HEAD_OFFICE_HOURS, HEAD_OFFICE_DAYS) if is_head_office(cost_center) else (SITE_HOURS, SITE_DAYS)
			row = rows[(slip.employee, slip.cost_center)] = frappe._dict(
				employee=slip.employee,
				employee_name=slip.employee_name,
				cost_center=cost_center.cost_center_name or _("Not Set"),
				employee_category=get_category(slip),
				daily_hours=daily_hours,
				monthly_hours=MONTH_DAYS * daily_hours,
				hour_days=days,
				months=0,
				gross_total=0.0,
				total_days=0.0,
				days_worked=0.0,
				ot_hours=0.0,
				ot_amount=0.0,
				currency=currency,
				usd="USD",
				**CONSTANTS,
				**employees.get(slip.employee, {}),
			)
		row.months += 1
		row.gross_total += gross.get(slip.salary_slip, 0.0)
		row.total_days += flt(slip.total_working_days)
		row.days_worked += flt(slip.payment_days)
		row.ot_hours += overtime.get(slip.salary_slip, 0.0)
		row.ot_amount += sum(
			flt(d.amount)
			for d in details.get(slip.salary_slip, [])
			if d.parentfield == "earnings" and classify(d) == "Overtime"
		)

	data = []
	for row in sorted(rows.values(), key=lambda r: (r.cost_center.lower(), r.employee)):
		row.gross_salary = flt(row.gross_total / row.months, 3)
		row.gross_salary_usd = flt(row.gross_salary * usd_rate, 3)
		row.total_working_hours = row.total_days * row.daily_hours
		row.compensation_per_hour = flt(row.gross_salary_usd / (row.hour_days * row.daily_hours), 3)
		row.ot_hours = flt(row.ot_hours, 2)
		row.total_hours_worked = row.days_worked * row.daily_hours + row.ot_hours
		row.total_compensation_usd = flt(row.compensation_per_hour * row.total_hours_worked, 3)
		for field in ("months", "gross_total", "total_days", "days_worked", "hour_days"):
			del row[field]
		data.append(row)
	return data


def is_head_office(cost_center):
	if cost_center.get("is_head_office"):
		return True
	name = (cost_center.cost_center_name or "").strip().lower()
	return name in ("ho", "head office") or name.startswith("head office")


def get_category(slip):
	# employees without a nationality are counted as Expat
	return slip.get("employee_category") or get_employee_category(slip.get("nationality")) or "Expat"


def get_salary_slips(filters, from_date, to_date):
	ss = frappe.qb.DocType("Salary Slip")
	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	pe = frappe.qb.DocType("Payroll Entry")
	cost_center = salary_slip_cost_center(pe, emp, dept)

	query = (
		frappe.qb.from_(ss)
		.join(emp)
		.on(ss.employee == emp.name)
		.left_join(dept)
		.on(emp.department == dept.name)
		.left_join(pe)
		.on(ss.payroll_entry == pe.name)
		.select(
			ss.name.as_("salary_slip"),
			ss.employee,
			ss.employee_name,
			ss.start_date,
			ss.end_date,
			ss.total_working_days,
			ss.payment_days,
			cost_center.as_("cost_center"),
		)
		.where(
			(ss.docstatus == 1)
			& (ss.company == filters.company)
			& (ss.start_date >= from_date)
			& (ss.start_date <= to_date)
		)
	)
	if has_employee_category():
		query = query.select(emp.employee_category)
	nationality = get_nationality_field()
	if nationality:
		query = query.select(emp[nationality].as_("nationality"))

	if filters.payroll_cost_center:
		cost_centers = [
			filters.payroll_cost_center,
			*(frappe.db.get_descendants("Cost Center", filters.payroll_cost_center) or []),
		]
		query = query.where(cost_center.isin(cost_centers))

	return query.run(as_dict=True)


def get_overtime_hours(slips):
	"""{salary_slip: OT hours} from the overtime recorded on the attendance of the slip's period."""
	if not frappe.get_meta("Attendance").has_field("actual_overtime_duration"):
		return {}

	attendance = {}
	for d in frappe.get_all(
		"Attendance",
		filters={
			"employee": ("in", list({s.employee for s in slips})),
			"docstatus": 1,
			"attendance_date": ("between", [min(s.start_date for s in slips), max(s.end_date for s in slips)]),
			"actual_overtime_duration": (">", 0),
		},
		fields=["employee", "attendance_date", "actual_overtime_duration"],
	):
		attendance.setdefault(d.employee, []).append(d)

	hours = {}
	for slip in slips:
		seconds = sum(
			flt(d.actual_overtime_duration)
			for d in attendance.get(slip.employee, [])
			if getdate(slip.start_date) <= getdate(d.attendance_date) <= getdate(slip.end_date)
		)
		hours[slip.salary_slip] = seconds / 3600
	return hours


def get_employee_details(employees):
	"""{employee: civil_id, nationality, qualification, icv_job_category, icv_designation}.

	ICV Job Category / ICV Designation are the Employee's (else the Designation's) fields with
	"ICV" in the label; without them, the Job Category and Designation are shown.
	"""
	employee_meta = frappe.get_meta("Employee")
	designation_meta = frappe.get_meta("Designation")
	id_field = next((f for f in ID_FIELDS if employee_meta.has_field(f)), None) or find_field(employee_meta, "civil", fieldtypes=("Data",))
	nationality = get_nationality_field()
	qualification = find_field(employee_meta, "qualification")
	icv_category = find_field(employee_meta, "icv", "categ")
	icv_designation = find_field(employee_meta, "icv", "design") or find_field(employee_meta, "icv", "sub")
	designation_category = find_field(designation_meta, "icv", "categ")
	designation_icv = find_field(designation_meta, "icv", "design") or find_field(designation_meta, "icv", "sub")
	job_category = "job_category" if employee_meta.has_field("job_category") else None

	fields = ["name", "designation"] + [
		f for f in {id_field, nationality, qualification, icv_category, icv_designation, job_category} if f
	]
	rows = frappe.get_all("Employee", filters={"name": ("in", list(employees))}, fields=fields)

	designations = {}
	if designation_category or designation_icv:
		designations = {
			d.name: d
			for d in frappe.get_all(
				"Designation",
				filters={"name": ("in", list({r.designation for r in rows if r.designation}))},
				fields=["name"] + [f for f in (designation_category, designation_icv) if f],
			)
		}
	education = get_education(employees) if not qualification else {}

	details = {}
	for r in rows:
		designation = designations.get(r.designation) or {}
		details[r.name] = {
			"civil_id": r.get(id_field) if id_field else None,
			"nationality": r.get(nationality) if nationality else None,
			"qualification": r.get(qualification) if qualification else education.get(r.name),
			"icv_job_category": (icv_category and r.get(icv_category))
			or (designation_category and designation.get(designation_category))
			or (job_category and r.get(job_category)),
			"icv_designation": (icv_designation and r.get(icv_designation))
			or (designation_icv and designation.get(designation_icv))
			or r.designation,
		}
	return details


def get_education(employees):
	"""{employee: qualification} - the latest passed qualification in the Education table."""
	education = {}
	for d in frappe.get_all(
		"Employee Education",
		filters={"parenttype": "Employee", "parent": ("in", list(employees))},
		fields=["parent", "qualification", "level"],
		order_by="year_of_passing asc, idx asc",
	):
		if d.qualification or d.level:
			education[d.parent] = d.qualification or d.level
	return education


def find_field(meta, *words, fieldtypes=None):
	"""Fieldname of the first value field (of `fieldtypes`, if given) whose label contains all `words`."""
	for df in meta.fields:
		label = (df.label or "").lower()
		if fieldtypes and df.fieldtype not in fieldtypes:
			continue
		if df.fieldtype not in NO_VALUE_TYPES and all(word in label for word in words):
			return df.fieldname
