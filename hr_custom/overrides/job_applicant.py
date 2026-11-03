"""Create Employee (from Job Offer / Employee Onboarding): fill the employee from the Job Applicant.

HRMS only copies the name and email. Here every Job Applicant field is copied to the Employee
field with the same fieldname or label (the site's own applicant fields - date of birth, gender,
passport, ... - included), plus phone and the Job Opening's department / designation. Values
already on the new employee (from the offer / onboarding) are kept.
"""

import frappe
from frappe.utils import cstr

# applicant-only fields that mean something else (or nothing) on an employee
SKIP_FIELDS = {
	"status",
	"job_title",
	"source",
	"source_name",
	"cover_letter",
	"notes",
	"resume_link",
	"applicant_rating",
	"lower_range",
	"upper_range",
	"currency",
	"employee_referral",
	"naming_series",
	"amended_from",
	"workflow_state",
	"applicant_name",
}
FIELD_MAP = {"email_id": "personal_email", "phone_number": "cell_number"}
NO_VALUE_TYPES = ("Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table", "Table MultiSelect", "Fold", "Heading")
TEXT_TYPES = ("Data", "Small Text", "Text", "Long Text", "Text Editor", "Phone")


@frappe.whitelist()
def make_employee_from_job_offer(source_name, target_doc=None):
	from hrms.hr.doctype.job_offer.job_offer import make_employee

	employee = make_employee(source_name, target_doc)
	set_applicant_details(employee, frappe.db.get_value("Job Offer", source_name, "job_applicant"))
	return employee


@frappe.whitelist()
def make_employee_from_onboarding(source_name, target_doc=None):
	from hrms.hr.doctype.employee_onboarding.employee_onboarding import make_employee

	employee = make_employee(source_name, target_doc)
	set_applicant_details(employee, frappe.db.get_value("Employee Onboarding", source_name, "job_applicant"))
	return employee


def before_insert(doc, method=None):
	"""Employee created some other way (e.g. by hand) with a Job Applicant set."""
	if doc.get("job_applicant"):
		set_applicant_details(doc, doc.job_applicant)


def set_applicant_details(employee, job_applicant):
	if not job_applicant or not frappe.db.exists("Job Applicant", job_applicant):
		return
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	employee_meta = frappe.get_meta("Employee")
	if employee_meta.has_field("job_applicant") and not employee.get("job_applicant"):
		employee.job_applicant = job_applicant

	for source, target in get_field_pairs(applicant.meta, employee_meta):
		value = applicant.get(source.fieldname)
		if value in (None, "") or employee.get(target.fieldname) not in (None, "", 0):
			continue
		if target.fieldtype == "Select" and cstr(value) not in (target.options or "").split("\n"):
			continue
		employee.set(target.fieldname, value)

	opening = applicant.get("job_title") and frappe.db.get_value(
		"Job Opening", applicant.job_title, ["department", "designation", "company"], as_dict=True
	)
	for field, value in (opening or {}).items():
		if value and not employee.get(field):
			employee.set(field, value)


def get_field_pairs(source_meta, target_meta):
	"""(applicant field, employee field) with the same fieldname or label and a compatible type."""
	by_label = {}
	for df in target_meta.fields:
		if df.fieldtype not in NO_VALUE_TYPES and df.label:
			by_label.setdefault(df.label.strip().lower(), df)

	pairs = []
	for source in source_meta.fields:
		if source.fieldtype in NO_VALUE_TYPES or source.fieldname in SKIP_FIELDS:
			continue
		target = (
			target_meta.get_field(FIELD_MAP.get(source.fieldname, source.fieldname))
			or by_label.get((source.label or "").strip().lower())
		)
		if target and target.fieldtype not in NO_VALUE_TYPES and not target.read_only and compatible(source, target):
			pairs.append((source, target))
	return pairs


def compatible(source, target):
	if source.fieldtype in TEXT_TYPES and target.fieldtype in TEXT_TYPES + ("Select",):
		return True
	if source.fieldtype != target.fieldtype:
		return source.fieldtype == "Select" and target.fieldtype in ("Select", "Data")
	if source.fieldtype == "Link":
		return source.options == target.options
	return True
