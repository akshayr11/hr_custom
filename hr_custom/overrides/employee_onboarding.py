"""Employee Onboarding: Visa Details and Ticket Details tabs.

Both stay editable after the onboarding is submitted (visa processing / travel continue after it).
On save, an empty visa Name is taken from the employee / applicant, and the Labor Clearance from the
Job Requisition the applicant was hired against (Job Applicant -> Job Opening -> Job Requisition).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPE = "Employee Onboarding"
CLEARANCE = "Labor Clearance"


def validate(doc, method=None):
	if doc.meta.has_field("visa_name") and not doc.visa_name:
		doc.visa_name = doc.employee_name or (
			doc.job_applicant and frappe.db.get_value("Job Applicant", doc.job_applicant, "applicant_name")
		)

	if doc.meta.has_field("visa_labor_clearance") and not doc.visa_labor_clearance:
		doc.visa_labor_clearance = get_labor_clearance(doc.job_applicant)


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

	# Labor Clearance is a site doctype; without it the clearance no. is typed in
	if frappe.db.exists("DocType", CLEARANCE):
		clearance = [
			field("visa_labor_clearance", "Link", "Desig As per Clearance", options=CLEARANCE),
			field(
				"visa_labor_clearance_no",
				"Data",
				"Labor Clearance No",
				fetch_from="visa_labor_clearance.job_code_as_per_clearance",
				fetch_if_empty=1,
			),
		]
	else:
		clearance = [
			field("visa_labor_clearance_no", "Data", "Labor Clearance No"),
			field("visa_designation_as_per_clearance", "Link", "Desig As per Clearance", options="Designation"),
		]

	visa = [
		{"fieldname": "visa_details_tab", "fieldtype": "Tab Break", "label": "Visa Details"},
		field("visa_name", "Data", "Name"),
		field("visa_status", "Select", "Visa Status", options="New\nIn Process\nApproved\nIssued\nRejected\nCancelled", default="New", in_standard_filter=1),
		field("visa_passport_no", "Data", "Passport No"),
		field("visa_place_of_birth", "Data", "Place of Birth"),
		field("visa_place_of_issue", "Data", "Place of Issue"),
		field("visa_issued_country", "Link", "Issued Country", options="Country"),
		field("visa_passport_issue_date", "Date", "Date of Issue"),
		field("visa_passport_expiry_date", "Date", "Date of Expiry"),
		{"fieldname": "visa_column_break", "fieldtype": "Column Break"},
		field("visa_type", "Select", "Type of Visa", options="\nEmployment Visa\nFamily Joining Visa\nVisit Visa\nBusiness Visa"),
		field("visa_father_name", "Data", "Father's Name"),
		field("visa_mother_name", "Data", "Mother's Name"),
		*clearance,
	]
	ticket = [
		{"fieldname": "ticket_details_tab", "fieldtype": "Tab Break", "label": "Ticket Details"},
		field("ticket_no", "Data", "Ticket No"),
		field("ticket_issue_date", "Date", "Issue Date"),
		field("ticket_arrival_date", "Date", "Arrival Date"),
		field("ticket_arrival_time", "Time", "Arrival Time"),
		field("ticket_amount", "Currency", "Ticket Amount"),
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
	create_custom_fields({DOCTYPE: fields}, update=True)
