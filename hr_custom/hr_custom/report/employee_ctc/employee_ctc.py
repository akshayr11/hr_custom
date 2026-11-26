# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee CTC (ALG format): monthly cost to company per employee, from the submitted salary
slips of the month.

* Gross / Net: the salary slip. Basic: its basic earning (as in Payroll Additions and Deductions);
  Allowances = Gross - Basic.
* The cost columns are set in Employee CTC Settings (salary component of the slip, % of basic /
  gross, monthly or annual amount, per employee category). A column without settings:
  - Employee Contr PASI / Security Fund: the PASI / Security Fund deductions of the slip.
  - Air Fare: the airfare earning of the slip.
  - Gratuity: the month's gratuity provision for Expats (gratuity at month end - gratuity at the
    end of the previous month, with the EOS Statement calculation on the full month basic).
  - Leave Salary: full month basic (or gross) / 30 x leave days per year / 12.
  - The others: 0.
* Total CTC = Gross + the company's costs. Amounts already in Gross (earnings of the slip) and
  the employee's own contributions (deductions of the slip) are not added again.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, get_last_day, getdate

from hr_custom.hr_custom.report.payroll_additions_and_deductions.payroll_additions_and_deductions import (
	get_classifier,
)
from hr_custom.utils import (
	EMPLOYEE_LOCATION_FIELD,
	get_employee_category,
	get_nationality_field,
	salary_slip_cost_center,
)

# report columns worked out from the settings (or their defaults), in the ALG order
COST_COLUMNS = [
	"Employee Contr PASI",
	"Employer Contr PASI",
	"Security Fund",
	"Gratuity",
	"GSM",
	"Air Fare",
	"Visa Cost",
	"Medical Insurance Cost",
	"Workmens Compensation",
	"Food Accomodation Cost",
	"Leave Salary",
]
# the employee's own contribution: shown, never part of the CTC
EMPLOYEE_SHARE = ("Employee Contr PASI",)
# classifier column (Payroll Additions and Deductions) used when a column has no settings
DEFAULT_SLIP_COLUMN = {"Employee Contr PASI": "PASI", "Security Fund": "Sec Fund", "Air Fare": "Airfare"}
DAYS_IN_MONTH = 30


def key(label):
	return frappe.scrub(label)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.month or not cint(filters.year):
		frappe.throw(_("Please set Company, Month and Year"))
	return get_columns(), get_data(filters)


def get_columns():
	def col(label, fieldtype="Data", width=110, fieldname=None, **kw):
		return {"label": _(label), "fieldname": fieldname or key(label), "fieldtype": fieldtype, "width": width, **kw}

	def money(label, width=120):
		return col(label, "Currency", width, options="currency")

	return [
		col("Location", width=120),
		col("Emp No", "Link", 120, "employee", options="Employee"),
		col("Employee Name", width=180),
		col("Job Title", "Link", 150, "designation", options="Designation"),
		col("Nationality", width=100),
		col("Date of Join", "Date", 100, "date_of_joining"),
		money("Gross Salary"),
		money("Net Salary"),
		money("Basic Salary"),
		money("Allowances"),
		*[money(label) for label in COST_COLUMNS],
		money("Total CTC", 130),
		money("Annual CTC", 130),
		col("Salary Slip", "Link", 170, options="Salary Slip"),
		col("Currency", "Link", 80, options="Currency", hidden=1),
	]


def get_data(filters):
	month = list(calendar.month_name).index(filters.month)
	start = getdate(f"{cint(filters.year)}-{month:02d}-01")
	end = get_last_day(start)
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	slips = get_salary_slips(filters, start, end)
	if not slips:
		return []
	details = get_slip_details([d.salary_slip for d in slips])
	settings = frappe.get_cached_doc("Employee CTC Settings")
	classify = get_classifier()

	data = []
	for slip in slips:
		category = slip.get("employee_category") or get_employee_category(slip.nationality)
		if filters.employee_category in ("Omani", "Expat") and category != filters.employee_category:
			continue
		data.append(get_row(slip, category, details.get(slip.salary_slip, []), settings, classify, start, end, currency))
	return data


def get_row(slip, category, details, settings, classify, start, end, currency):
	row = frappe._dict(
		location=slip.location,
		employee=slip.employee,
		employee_name=slip.employee_name,
		designation=slip.designation,
		nationality=slip.nationality,
		date_of_joining=slip.date_of_joining,
		gross_salary=flt(slip.gross_pay),
		net_salary=flt(slip.net_pay),
		salary_slip=slip.salary_slip,
		currency=currency,
	)

	in_gross = lambda d: d.parentfield == "earnings" and not d.statistical_component and not d.do_not_include_in_total  # noqa: E731
	basic_rows = [d for d in details if in_gross(d) and classify(d) == "Basic Salary"]
	row.basic_salary = flt(sum(flt(d.amount) for d in basic_rows), 3)
	row.allowances = flt(row.gross_salary - row.basic_salary, 3)
	full_basic = sum(flt(d.default_amount or d.amount) for d in basic_rows)
	full_gross = sum(flt(d.default_amount or d.amount) for d in details if in_gross(d) and not d.additional_salary)

	company_cost = 0
	for label in COST_COLUMNS:
		rules = [r for r in settings.costs if r.ctc_column == label and r.employee_category in ("All", category)]
		amount = cost = 0
		if rules:
			for rule in rules:
				value, is_company_cost = get_rule_amount(rule, row, details)
				amount += value
				cost += value if is_company_cost else 0
		elif label in DEFAULT_SLIP_COLUMN:
			# the slip's own earning (already in Gross) or deduction (the employee's): not added
			amount = sum(
				flt(d.amount)
				for d in details
				if not d.statistical_component and classify(d) == DEFAULT_SLIP_COLUMN[label]
			)
		elif label == "Gratuity":
			amount = cost = get_gratuity_provision(slip, category, full_basic, start, end)
		elif label == "Leave Salary":
			basis = full_gross if settings.leave_salary_based_on == "Gross Salary" else full_basic
			amount = cost = basis / DAYS_IN_MONTH * flt(settings.leave_days_per_year) / 12

		row[key(label)] = flt(amount, 3)
		if label not in EMPLOYEE_SHARE:
			company_cost += cost

	row.total_ctc = flt(row.gross_salary + company_cost, 3)
	row.annual_ctc = flt(row.total_ctc * 12, 3)
	return row


def get_rule_amount(rule, row, details):
	"""(amount, company cost): a slip earning is already in Gross and a slip deduction is the
	employee's, so only a statistical component of the slip adds to the CTC."""
	if rule.based_on == "Salary Component":
		rows = [d for d in details if d.salary_component == rule.salary_component]
		amount = sum(flt(d.amount) for d in rows)
		return amount, any(d.statistical_component or (d.parentfield == "earnings" and d.do_not_include_in_total) for d in rows)
	if rule.based_on == "% of Basic Salary":
		return flt(row.basic_salary) * flt(rule.rate) / 100, True
	if rule.based_on == "% of Gross Salary":
		return flt(row.gross_salary) * flt(rule.rate) / 100, True
	if rule.based_on == "Monthly Amount":
		return flt(rule.amount), True
	if rule.based_on == "Annual Amount":
		return flt(rule.amount) / 12, True
	return 0, False


def get_gratuity_provision(slip, category, basic, start, end):
	"""Gratuity earned in the month (Expats): gratuity at month end - at the previous month end."""
	from hr_custom.hr_custom.doctype.eos_statement.eos_statement import calculate_gratuity

	if category != "Expat" or not basic or not slip.date_of_joining:
		return 0
	doj = getdate(slip.date_of_joining)
	if doj > end:
		return 0

	def total(till):
		if date_diff(till, doj) < 0:
			return 0
		result = calculate_gratuity(slip.employee, doj, till, current_basic=basic)
		return sum(flt(d["amount"]) for d in result["details"])

	try:
		return total(end) - total(add_days(start, -1))
	except Exception:
		frappe.clear_messages()
		return 0


def get_salary_slips(filters, start, end):
	ss = frappe.qb.DocType("Salary Slip")
	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	pe = frappe.qb.DocType("Payroll Entry")
	meta = frappe.get_meta("Employee")

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
			ss.gross_pay,
			ss.net_pay,
			emp.employee_name,
			emp.designation,
			emp.department,
			emp.date_of_joining,
		)
		.where(
			(ss.docstatus == 1)
			& (ss.company == filters.company)
			& (ss.start_date >= start)
			& (ss.start_date <= end)
		)
		.orderby(emp.name)
		.orderby(ss.start_date)
	)

	location_field = EMPLOYEE_LOCATION_FIELD if meta.has_field(EMPLOYEE_LOCATION_FIELD) else "branch"
	query = query.select(emp[location_field].as_("location"))
	nationality = get_nationality_field()
	if nationality:
		query = query.select(emp[nationality].as_("nationality"))
	if meta.has_field("employee_category"):
		query = query.select(emp.employee_category)

	if filters.location:
		query = query.where(emp[location_field] == filters.location)
	if filters.payroll_cost_center:
		cost_centers = [
			filters.payroll_cost_center,
			*(frappe.db.get_descendants("Cost Center", filters.payroll_cost_center) or []),
		]
		query = query.where(salary_slip_cost_center(pe, emp, dept).isin(cost_centers))
	if filters.department:
		query = query.where(emp.department == filters.department)
	if filters.designation:
		query = query.where(emp.designation == filters.designation)
	if filters.employee:
		query = query.where(ss.employee == filters.employee)

	slips = query.run(as_dict=True)
	for d in slips:
		d.setdefault("nationality", None)
	# one row per employee: the latest slip of the month
	return list({d.employee: d for d in slips}.values())


def get_slip_details(salary_slips):
	sd = frappe.qb.DocType("Salary Detail")
	rows = (
		frappe.qb.from_(sd)
		.select(
			sd.parent,
			sd.parentfield,
			sd.salary_component,
			sd.amount,
			sd.default_amount,
			sd.additional_salary,
			sd.statistical_component,
			sd.do_not_include_in_total,
		)
		.where((sd.parenttype == "Salary Slip") & (sd.parent.isin(salary_slips)))
		.orderby(sd.idx)
	).run(as_dict=True)

	details = {}
	for d in rows:
		details.setdefault(d.parent, []).append(d)
	return details
