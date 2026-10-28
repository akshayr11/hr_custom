"""Job Offer: 'Save Details from Offer' for the employee created from the offer.

- The Leave Policy chosen in the offer (field 'Leave Cycle') is assigned to the employee from their
  date of joining and its leaves are allocated.
- A Salary Structure is made from the salary amounts in the offer, submitted and assigned to the
  employee from their date of joining (base = Basic).

The offer's leave / salary fields are site fields, so they are found by type and label:
- leave policy: a Link to Leave Policy (or a field labelled 'leave' holding a Leave Policy name);
- salary: Currency / Float fields whose label matches an Earning Salary Component (name or
  abbreviation), rows of a child table with a Salary Component link and an amount, or Offer Terms
  whose term matches a component and whose value is a number.
"""

import re

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_last_day, getdate

from hr_custom.overrides.salary_structure_assignment import AIRFARE_COMPONENT

AMOUNT_TYPES = ("Currency", "Float", "Int")
# offer fields that are totals, not components
TOTAL_WORDS = ("gross", "total", "ctc", "net", "package")


@frappe.whitelist()
def get_offer_details(job_offer):
	"""What 'Save Details from Offer' will create (shown to the user before saving)."""
	offer = get_offer(job_offer)
	employee = get_employee(offer)
	details = frappe._dict(
		employee=employee.name,
		employee_name=employee.employee_name,
		date_of_joining=employee.date_of_joining,
		leave_policy=get_leave_policy(offer),
		components=get_salary_components(offer),
		existing_leave_policy_assignment=get_existing_leave_assignment(employee.name),
		existing_salary_structure_assignment=get_existing_salary_assignment(employee.name),
	)
	details.basic = get_basic_amount(details.components)
	return details


@frappe.whitelist()
def save_details_from_offer(job_offer):
	details = get_offer_details(job_offer)
	offer = get_offer(job_offer)
	employee = frappe.get_doc("Employee", details.employee)
	created = []

	if details.leave_policy and not details.existing_leave_policy_assignment:
		created.append(make_leave_policy_assignment(employee, details.leave_policy))

	if details.components and not details.existing_salary_structure_assignment:
		structure = make_salary_structure(employee, offer, details.components)
		created.append(structure)
		created.append(make_salary_structure_assignment(employee, structure, details.basic))

	return [{"doctype": d.doctype, "name": d.name} for d in created]


def get_offer(job_offer):
	offer = frappe.get_doc("Job Offer", job_offer)
	offer.check_permission("write")
	if offer.docstatus != 1:
		frappe.throw(_("Job Offer must be approved (submitted) first"))
	return offer


def get_employee(offer):
	employee = frappe.db.get_value(
		"Employee",
		{"job_applicant": offer.job_applicant},
		["name", "employee_name", "company", "date_of_joining"],
		as_dict=True,
	)
	if not employee:
		frappe.throw(_("Create the Employee from this Job Offer first"))
	if not employee.date_of_joining:
		frappe.throw(_("Set the Date of Joining of Employee {0} first").format(employee.name))
	return employee


# ---------- leave policy ----------


def get_leave_policy(offer):
	for df in offer.meta.fields:
		if df.fieldtype == "Link" and df.options == "Leave Policy" and offer.get(df.fieldname):
			return offer.get(df.fieldname)

	# e.g. a Select / Data 'Leave Cycle' holding the policy name
	for df in offer.meta.fields:
		value = offer.get(df.fieldname)
		if (
			df.fieldtype in ("Select", "Data", "Link")
			and "leave" in f"{df.fieldname} {df.label or ''}".lower()
			and isinstance(value, str)
			and frappe.db.exists("Leave Policy", {"name": value, "docstatus": 1})
		):
			return value


def get_existing_leave_assignment(employee):
	return frappe.db.get_value(
		"Leave Policy Assignment",
		{"employee": employee, "docstatus": 1},
		["name", "leave_policy", "effective_from", "effective_to"],
		as_dict=True,
		order_by="effective_from desc",
	)


def make_leave_policy_assignment(employee, leave_policy):
	doj = getdate(employee.date_of_joining)
	assignment = frappe.new_doc("Leave Policy Assignment")
	assignment.update(
		{"employee": employee.name, "company": employee.company, "leave_policy": leave_policy}
	)

	leave_period = frappe.db.get_value(
		"Leave Period",
		{"company": employee.company, "is_active": 1, "from_date": ("<=", doj), "to_date": (">=", doj)},
		["name", "to_date"],
		as_dict=True,
	)
	# allocation runs from joining to the end of the leave period (or 12 months when there is none)
	assignment.assignment_based_on = "Joining Date"
	assignment.effective_from = doj
	assignment.effective_to = leave_period.to_date if leave_period else get_last_day(add_months(doj, 12))

	assignment.insert()
	assignment.submit()
	return assignment


# ---------- salary ----------


def normalize(text):
	return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def get_earning_components():
	return frappe.get_all(
		"Salary Component",
		filters={"type": "Earning", "disabled": 0, "name": ("!=", AIRFARE_COMPONENT)},
		fields=["name", "salary_component_abbr"],
	)


def match_component(text, components):
	"""Component whose name / abbreviation is the text (or is contained in it, e.g. 'Basic Salary')."""
	key = normalize(text)
	if not key or any(w in key for w in TOTAL_WORDS):
		return None

	for c in components:
		if key in (normalize(c.name), normalize(c.salary_component_abbr)):
			return c.name
	for c in components:
		name = normalize(c.name)
		if len(name) >= 3 and (name in key or key in name):
			return c.name


def get_salary_components(offer):
	"""[{salary_component, amount, source}] from the offer, one row per component."""
	components = get_earning_components()
	found = {}

	def add(component, amount, source):
		if component and flt(amount) > 0 and component not in found:
			found[component] = frappe._dict(salary_component=component, amount=flt(amount), source=source)

	for df in offer.meta.fields:
		if df.fieldtype in AMOUNT_TYPES:
			add(match_component(df.label or df.fieldname, components), offer.get(df.fieldname), df.label)

		elif df.fieldtype == "Table" and df.options != "Job Offer Term":
			add_child_table_rows(offer, df, add)

	for term in offer.get("offer_terms") or []:
		amount = parse_amount(term.value)
		if amount is not None:
			add(match_component(term.offer_term, components), amount, term.offer_term)

	return list(found.values())


def add_child_table_rows(offer, df, add):
	"""Child table with a Salary Component link and an amount field."""
	meta = frappe.get_meta(df.options)
	link = next((f.fieldname for f in meta.fields if f.fieldtype == "Link" and f.options == "Salary Component"), None)
	amount = next((f.fieldname for f in meta.fields if f.fieldtype in AMOUNT_TYPES), None)
	if not link or not amount:
		return
	for row in offer.get(df.fieldname) or []:
		component = row.get(link)
		if component and frappe.db.get_value("Salary Component", component, "type") == "Earning":
			add(component, row.get(amount), _(df.label))


def parse_amount(value):
	text = frappe.utils.strip_html(value or "").replace(",", "")
	numbers = re.findall(r"\d+(?:\.\d+)?", text)
	# a term like 'Basic: 300 OMR' -> 300; free text with several numbers is not an amount
	return flt(numbers[0]) if len(numbers) == 1 else None


def get_basic_amount(components):
	basic = frappe.db.get_single_value("Employee Warning Settings", "basic_component")
	for d in components:
		if d.salary_component == basic or (not basic and "basic" in d.salary_component.lower()):
			return d.amount
	return 0


def get_existing_salary_assignment(employee):
	return frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1},
		["name", "salary_structure", "from_date", "base"],
		as_dict=True,
		order_by="from_date desc",
	)


def make_salary_structure(employee, offer, components):
	name = f"{employee.employee_name or employee.name} - {employee.name}"
	if frappe.db.exists("Salary Structure", name):
		name = f"{name} - {offer.name}"

	structure = frappe.new_doc("Salary Structure")
	structure.update(
		{
			"__newname": name,
			"name": name,
			"company": employee.company,
			"payroll_frequency": "Monthly",
			"currency": frappe.get_cached_value("Company", employee.company, "default_currency"),
			"is_active": "Yes",
		}
	)
	for d in components:
		structure.append(
			"earnings",
			{"salary_component": d.salary_component, "amount_based_on_formula": 0, "amount": d.amount},
		)
	structure.insert()
	structure.submit()
	return structure


def make_salary_structure_assignment(employee, structure, base):
	assignment = frappe.new_doc("Salary Structure Assignment")
	assignment.update(
		{
			"employee": employee.name,
			"salary_structure": structure.name,
			"company": employee.company,
			"currency": structure.currency,
			"from_date": employee.date_of_joining,
			"base": base,
		}
	)
	assignment.insert()
	assignment.submit()
	return assignment
