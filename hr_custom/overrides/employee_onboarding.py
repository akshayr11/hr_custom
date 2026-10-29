"""Employee Onboarding: Visa Details and Ticket Details tabs (Data fields except dates, Visa Status and
the Labor Clearance link).

Both stay editable after the onboarding is submitted (visa processing / travel continue after it).
Passport details are copied to the employee (Personal Details > Passport Details).
On save, an empty visa Name is taken from the employee / applicant, and the Labor Clearance from the
Job Requisition the applicant was hired against (Job Applicant -> Job Opening -> Job Requisition).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPE = "Employee Onboarding"
CLEARANCE = "Labor Clearance"
# onboarding Visa Details -> Employee Passport Details
PASSPORT_FIELDS = {
	"visa_passport_no": "passport_number",
	"visa_passport_issue_date": "date_of_issue",
	"visa_passport_expiry_date": "valid_upto",
	"visa_place_of_issue": "place_of_issue",
}


def validate(doc, method=None):
	if doc.meta.has_field("visa_name") and not doc.visa_name:
		doc.visa_name = doc.employee_name or (
			doc.job_applicant and frappe.db.get_value("Job Applicant", doc.job_applicant, "applicant_name")
		)

	if doc.meta.has_field("visa_labor_clearance") and not doc.visa_labor_clearance:
		doc.visa_labor_clearance = get_labor_clearance(doc.job_applicant)


def on_update(doc, method=None):
	"""Passport details entered in the onboarding are copied to its employee."""
	if not doc.employee:
		return
	values = {emp_field: doc.get(field) for field, emp_field in PASSPORT_FIELDS.items() if doc.get(field)}
	current = frappe.db.get_value("Employee", doc.employee, list(values), as_dict=True) if values else {}
	changed = {k: v for k, v in values.items() if str(current.get(k) or "") != str(v)}
	if changed:
		frappe.db.set_value("Employee", doc.employee, changed)


def set_employee_passport_details(doc, method=None):
	"""Employee validate: fill empty passport fields from the applicant's onboarding (e.g. an employee
	created from the onboarding)."""
	if not doc.job_applicant or not frappe.get_meta(DOCTYPE).has_field("visa_passport_no"):
		return
	onboarding = frappe.db.get_value(
		DOCTYPE,
		{"job_applicant": doc.job_applicant, "docstatus": ("<", 2)},
		list(PASSPORT_FIELDS),
		as_dict=True,
		order_by="creation desc",
	)
	for field, emp_field in PASSPORT_FIELDS.items():
		if onboarding and onboarding.get(field) and not doc.get(emp_field):
			doc.set(emp_field, onboarding.get(field))


def get_labor_clearance(job_applicant):
	from hr_custom.overrides.job_requisition import get_clearance_field

	field = get_clearance_field(frappe.get_meta("Job Requisition"))
	if not field or not job_applicant:
		return None

	job_opening = frappe.db.get_value("Job Applicant", job_applicant, "job_title")
	requisition = job_opening and frappe.db.get_value("Job Opening", job_opening, "job_requisition")
	return requisition and frappe.db.get_value("Job Requisition", requisition, field)


def make_fields():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	def field(fieldname, fieldtype, label=None, **kw):
		return {"fieldname": fieldname, "fieldtype": fieldtype, "label": label, "allow_on_submit": 1, **kw}

	# Labor Clearance is a site doctype; a link to it can only be made where it exists
	clearance = (
		[field("visa_labor_clearance", "Link", "Desig As per Clearance", options=CLEARANCE)]
		if frappe.db.exists("DocType", CLEARANCE)
		else []
	)
	# replaced by the Labor Clearance link
	if frappe.db.exists("Custom Field", f"{DOCTYPE}-visa_designation_as_per_clearance"):
		frappe.delete_doc("Custom Field", f"{DOCTYPE}-visa_designation_as_per_clearance", force=1)

	visa = [
		{"fieldname": "visa_details_tab", "fieldtype": "Tab Break", "label": "Visa Details"},
		field("visa_name", "Data", "Name"),
		field(
			"visa_status",
			"Select",
			"Visa Status",
			options="New\nApplied\nReady\nSent\nDeposited\nCancelled",
			default="New",
			in_standard_filter=1,
		),
		field("visa_passport_no", "Data", "Passport No"),
		field("visa_place_of_birth", "Data", "Place of Birth"),
		field("visa_place_of_issue", "Data", "Place of Issue"),
		field("visa_issued_country", "Data", "Issued Country"),
		field("visa_passport_issue_date", "Date", "Date of Issue"),
		field("visa_passport_expiry_date", "Date", "Date of Expiry"),
		{"fieldname": "visa_column_break", "fieldtype": "Column Break"},
		field("visa_type", "Data", "Type of Visa"),
		field("visa_father_name", "Data", "Father's Name"),
		field("visa_mother_name", "Data", "Mother's Name"),
		field(
			"visa_labor_clearance_no",
			"Data",
			"Labor Clearance No",
			fetch_from="visa_labor_clearance.job_code_as_per_clearance" if clearance else None,
			fetch_if_empty=1 if clearance else 0,
		),
		*clearance,
	]
	ticket = [
		{"fieldname": "ticket_details_tab", "fieldtype": "Tab Break", "label": "Ticket Details"},
		field("ticket_no", "Data", "Ticket No"),
		field("ticket_issue_date", "Date", "Issue Date"),
		field("ticket_arrival_date", "Date", "Arrival Date"),
		field("ticket_arrival_time", "Data", "Arrival Time"),
		field("ticket_amount", "Data", "Ticket Amount"),
		{"fieldname": "ticket_column_break", "fieldtype": "Column Break"},
		field("ticket_from_location", "Data", "From Location"),
		field("ticket_to_location", "Data", "To Location"),
		field("ticket_purchased_by", "Data", "Purchased By"),
		field("ticket_airline_name", "Data", "Airline Name"),
		field("ticket_agent_name", "Data", "Agent Name"),
	]

	# chain insert_after so the tabs come after the standard fields, in this order
	fields, previous = [], "amended_from"
	for df in visa + ticket:
		fields.append({**df, "insert_after": previous})
		previous = df["fieldname"]

	change_field_types(fields)
	create_custom_fields({DOCTYPE: fields}, update=True)
	frappe.db.updatedb(DOCTYPE)


def change_field_types(fields):
	"""Frappe refuses some type changes on save (e.g. Link -> Data), so fields made with an earlier
	type are switched directly; updatedb then changes the column."""
	for df in fields:
		name = f"{DOCTYPE}-{df['fieldname']}"
		if frappe.db.get_value("Custom Field", name, "fieldtype") not in (None, df["fieldtype"]):
			frappe.db.set_value("Custom Field", name, {"fieldtype": df["fieldtype"], "options": df.get("options")})
