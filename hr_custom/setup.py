import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


ROLES = ("IT Admin",)


def before_install():
	make_roles()


def before_migrate():
	# roles must exist before doctypes that grant them permissions are synced
	make_roles()


def after_install():
	make_custom_fields()
	make_it_masters()
	make_workflows()


def after_migrate():
	make_custom_fields()
	make_it_masters()
	make_workflows()


# default entries for the IT Service Request masters; only added when missing, so edits are kept
IT_MASTERS = {
	"IT Request Type": (
		"request_type",
		[
			{"request_type": "Network"},
			{"request_type": "Hardware", "requires_system_details": 1},
			{"request_type": "ERP", "requires_erp_module": 1},
			{"request_type": "Other IT Services"},
		],
	),
	"IT Computer Type": (
		"computer_type",
		[
			{"computer_type": t}
			for t in ("Computer", "Laptop", "Monitor", "Desktop PC", "Scanner", "Printer", "LED TV")
		],
	),
	"ERP Module": (
		"erp_module",
		[
			{"erp_module": m}
			for m in (
				"HR",
				"Payroll",
				"Accounts",
				"Buying",
				"Selling",
				"Stock",
				"Projects",
				"Assets",
				"Manufacturing",
				"CRM",
				"Other",
			)
		],
	),
}


def make_it_masters():
	for doctype, (key, records) in IT_MASTERS.items():
		for record in records:
			if not frappe.db.exists(doctype, record[key]):
				frappe.get_doc({"doctype": doctype, **record}).insert(ignore_permissions=True)


# OHB Bank Loan approval: Draft -> Pending Approval -> Approved (HR Manager). Only created when the
# doctype has no workflow yet, so changes made in the Workflow form are kept.
OHB_LOAN_WORKFLOW = {
	"workflow_name": "OHB Bank Loan",
	"document_type": "OHB Bank Loan",
	"workflow_state_field": "workflow_state",
	"is_active": 1,
	"send_email_alert": 0,
	"states": [
		{"state": "Draft", "doc_status": "0", "allow_edit": "HR User"},
		{"state": "Pending Approval", "doc_status": "0", "allow_edit": "HR Manager"},
		{"state": "Approved", "doc_status": "1", "allow_edit": "HR Manager"},
		{"state": "Rejected", "doc_status": "0", "allow_edit": "HR Manager"},
	],
	"transitions": [
		{"state": "Draft", "action": "Send for Approval", "next_state": "Pending Approval", "allowed": "HR User"},
		{"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "HR Manager"},
		{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "HR Manager"},
		{"state": "Rejected", "action": "Send for Approval", "next_state": "Pending Approval", "allowed": "HR User"},
	],
}


# Job Offer approval: Draft -> Pending Approval -> Approved (HR Manager). The offer's own Status
# (Awaiting Response / Accepted / ...) is left to the user, as HRMS needs it for Create Employee.
JOB_OFFER_WORKFLOW = {
	"workflow_name": "Job Offer",
	"document_type": "Job Offer",
	"workflow_state_field": "workflow_state",
	"is_active": 1,
	"send_email_alert": 0,
	"states": [
		{"state": "Draft", "doc_status": "0", "allow_edit": "HR User"},
		{"state": "Pending Approval", "doc_status": "0", "allow_edit": "HR Manager"},
		{"state": "Approved", "doc_status": "1", "allow_edit": "HR Manager"},
		{"state": "Rejected", "doc_status": "0", "allow_edit": "HR Manager"},
	],
	"transitions": [
		{"state": "Draft", "action": "Send for Approval", "next_state": "Pending Approval", "allowed": "HR User"},
		{"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "HR Manager"},
		{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "HR Manager"},
		{"state": "Rejected", "action": "Send for Approval", "next_state": "Pending Approval", "allowed": "HR User"},
	],
}


def make_workflows():
	for workflow in (OHB_LOAN_WORKFLOW, JOB_OFFER_WORKFLOW):
		make_workflow(workflow)


def make_ohb_loan_workflow():
	make_workflow(OHB_LOAN_WORKFLOW)


def make_job_offer_workflow():
	make_workflow(JOB_OFFER_WORKFLOW)


def make_workflow(workflow):
	"""Create the workflow unless the doctype already has one (edits made in the Workflow form are kept)."""
	if not frappe.db.exists("DocType", workflow["document_type"]):
		return
	if frappe.db.exists("Workflow", {"document_type": workflow["document_type"]}):
		return

	for state in workflow["states"]:
		if not frappe.db.exists("Workflow State", state["state"]):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state["state"]}).insert(
				ignore_permissions=True
			)
	for action in {t["action"] for t in workflow["transitions"]}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	frappe.get_doc({"doctype": "Workflow", **workflow}).insert(ignore_permissions=True)


def make_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def make_custom_fields():
	from hr_custom.utils import get_nationality_field

	make_nationality_field()
	nationality_field = get_nationality_field()
	create_custom_fields(
		{
			"Cost Center": [
				{
					"fieldname": "is_head_office",
					"fieldtype": "Check",
					"label": "Is Head Office",
					"insert_after": "is_group",
					"description": "Bank Letter allows department wise selection for Head Office cost centers",
				}
			],
			"Employee": [
				{
					"fieldname": "employee_category",
					"fieldtype": "Select",
					"label": "Employee Category",
					"options": "\nOmani\nExpat",
					"insert_after": nationality_field,
					"in_standard_filter": 1,
					"read_only": 1,
					"description": "Set from Nationality: Oman = Omani, any other = Expat",
				}
			],
			"Payroll Entry": [
				{
					"fieldname": "employee_category",
					"fieldtype": "Select",
					"label": "Employee Category",
					"options": "All\nOmani\nExpat",
					"default": "All",
					"insert_after": "grade",
				},
				{
					"fieldname": "payroll_cost_center",
					"fieldtype": "Link",
					"label": "Payroll Cost Center",
					"options": "Cost Center",
					"insert_after": "employee_category",
					"description": "Only employees whose Payroll Cost Center is this (or a child of it)",
				},
			],
			"Payroll Employee Detail": [
				{
					"fieldname": "employee_category",
					"fieldtype": "Data",
					"label": "Employee Category",
					"fetch_from": "employee.employee_category",
					"insert_after": "designation",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 1,
				},
				{
					"fieldname": "payroll_cost_center",
					"fieldtype": "Link",
					"label": "Payroll Cost Center",
					"options": "Cost Center",
					"fetch_from": "employee.payroll_cost_center",
					"insert_after": "employee_category",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 2,
				},
			],
			"Salary Component": [
				{
					"fieldname": "is_overtime_component",
					"fieldtype": "Check",
					"label": "Is Overtime (OT) Component",
					"insert_after": "depends_on_payment_days",
					"depends_on": "eval:doc.type=='Earning'",
					"description": "Used by Bank Letter to separate OT from salary",
				}
			],
		},
		update=True,
	)
	make_job_category_fields()
	make_property_setters()
	make_service_request_fields()
	make_airfare_component()
	make_workflow_user_fields()
	make_gratuity_fields()
	make_job_requisition_fields()
	make_employee_onboarding_fields()
	update_employee_categories()


def make_nationality_field():
	from hr_custom.utils import get_nationality_field

	# use the site's own nationality field (e.g. custom_nationality) if there is one
	if get_nationality_field():
		return

	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "nationality",
					"fieldtype": "Link",
					"label": "Nationality",
					"options": "Country",
					"insert_after": "employment_type",
					"in_standard_filter": 1,
				}
			]
		}
	)


def make_workflow_user_fields():
	from hr_custom.overrides.workflow_users import make_fields

	make_fields()


def make_job_requisition_fields():
	from hr_custom.overrides.job_requisition import make_fields

	make_fields()


def make_employee_onboarding_fields():
	from hr_custom.overrides.employee_onboarding import make_fields

	make_fields()


def make_gratuity_fields():
	from hr_custom.overrides.gratuity import make_fields

	make_fields()


def make_airfare_component():
	from hr_custom.overrides.salary_structure_assignment import make_airfare_component

	make_airfare_component()


def make_service_request_fields():
	from hr_custom.overrides.service_request import make_fields

	make_fields()


def make_job_category_fields():
	"""Job Category filter/column in Payroll Entry, mirroring Employee.job_category (if the site has it)."""
	df = frappe.get_meta("Employee").get_field("job_category")
	if not df:
		return

	fieldtype = df.fieldtype if df.fieldtype in ("Link", "Select") else "Data"
	options = df.options if fieldtype != "Data" else None
	create_custom_fields(
		{
			"Payroll Entry": [
				{
					"fieldname": "job_category",
					"fieldtype": fieldtype,
					"options": options,
					"label": "Job Category",
					"insert_after": "employee_category",
				}
			],
			"Payroll Employee Detail": [
				{
					"fieldname": "job_category",
					"fieldtype": fieldtype,
					"options": options,
					"label": "Job Category",
					"fetch_from": "employee.job_category",
					"insert_after": "employee_category",
					"read_only": 1,
					"in_list_view": 1,
					"columns": 2,
				}
			],
		},
		update=True,
	)


def update_employee_categories():
	"""Backfill Employee Category from Nationality for existing employees."""
	from frappe.query_builder import Case
	from frappe.query_builder.functions import Lower, Trim

	from hr_custom.utils import OMANI_NATIONALITIES, get_nationality_field

	fieldname = get_nationality_field()
	if not fieldname:
		return

	employee = frappe.qb.DocType("Employee")
	nationality_value = employee[fieldname]
	nationality = Lower(Trim(nationality_value))
	category = (
		Case()
		.when(nationality_value.isnull() | (nationality_value == ""), None)
		.when(nationality.isin(OMANI_NATIONALITIES), "Omani")
		.else_("Expat")
	)
	frappe.qb.update(employee).set(employee.employee_category, category).run()


def make_property_setters():
	# make room for Employee Category / Job Category / Payroll Cost Center in Payroll Entry's employee
	# grid (10 columns): Employee 2, Name 2, Category 1, Job Category 2, Cost Center 2, Withheld 1
	setters = [
		("designation", "in_list_view", 0, "Check"),
		("is_salary_withheld", "columns", 1, "Int"),
		("employee_name", "columns", 2, "Int"),
	]
	if frappe.get_meta("Employee").has_field("job_category"):
		setters.append(("department", "in_list_view", 0, "Check"))
	for fieldname, prop, value, property_type in setters:
		make_property_setter(
			"Payroll Employee Detail", fieldname, prop, value, property_type, validate_fields_for_doctype=False
		)


def diagnose():
	"""`bench --site <site> execute hr_custom.setup.diagnose` - shows what is missing for the
	Employee Category / Job Category / Payroll Cost Center features."""
	from hr_custom.utils import get_nationality_field

	expected = {
		"Employee": ["employee_category"],
		"Payroll Entry": ["employee_category", "payroll_cost_center", "job_category"],
		"Payroll Employee Detail": ["employee_category", "payroll_cost_center", "job_category"],
		"Cost Center": ["is_head_office"],
	}
	report = {"missing_fields": {}}
	for doctype, fields in expected.items():
		meta = frappe.get_meta(doctype)
		missing = [f for f in fields if not meta.has_field(f)]
		if missing:
			report["missing_fields"][doctype] = missing

	report["nationality_field"] = get_nationality_field()
	report["employee_has_job_category"] = frappe.get_meta("Employee").has_field("job_category")
	report["payroll_entry_extension_loaded"] = "PayrollEntryMixin" in [
		c.__name__ for c in frappe.get_doc({"doctype": "Payroll Entry"}).__class__.__mro__
	]

	active = {"status": "Active"}
	report["active_employees"] = frappe.db.count("Employee", active)
	if report["nationality_field"]:
		report["active_without_nationality"] = frappe.db.count(
			"Employee", {**active, report["nationality_field"]: ("is", "not set")}
		)
	if frappe.get_meta("Employee").has_field("employee_category"):
		report["active_without_category"] = frappe.db.count(
			"Employee", {**active, "employee_category": ("is", "not set")}
		)

	emp = frappe.qb.DocType("Employee")
	dept = frappe.qb.DocType("Department")
	from hr_custom.utils import employee_payroll_cost_center

	no_cc = (
		frappe.qb.from_(emp)
		.left_join(dept)
		.on(emp.department == dept.name)
		.select(emp.name, emp.employee_name)
		.where((emp.status == "Active") & employee_payroll_cost_center(emp, dept).isnull())
	).run()
	report["active_without_payroll_cost_center"] = [f"{d[0]} {d[1]}" for d in no_cc]

	from hr_custom.overrides.salary_structure_assignment import AIRFARE_COMPONENT, get_airfare_field

	airfare_field = get_airfare_field()
	report["airfare_field"] = airfare_field
	report["airfare_component_exists"] = bool(frappe.db.exists("Salary Component", AIRFARE_COMPONENT))
	report["airfare_component_accounts"] = frappe.get_all(
		"Salary Component Account", {"parent": AIRFARE_COMPONENT}, ["company", "account"]
	)
	if airfare_field:
		report["active_with_airfare"] = frappe.db.count("Employee", {**active, airfare_field: (">", 0)})
	import hrms

	report["hrms_version"] = getattr(hrms, "__version__", "?")

	for key, value in report.items():
		print(f"{key}: {value}")
