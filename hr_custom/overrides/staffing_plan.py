"""Staffing Plan for budgeted hiring, none for non-budgeted.

Budgeted = Yes: when the Job Requisition is approved (status Open & Approved, or an approved
workflow state) it is linked to the active Staffing Plan of its designation (company, posting
date), and must fit in that plan: its positions within the designation's vacancies, and its cost
(positions x expected compensation, else the plan's cost per position) within the designation's
estimated cost, less what the other approved requisitions of the plan already take.

Budgeted = No: hired for outside the staffing plan, so its Job Opening is not linked to (or
checked against) a Staffing Plan, and the Job Offers for its applicants are not checked against
staffing plan vacancies / budget.

Path: Job Offer -> Job Applicant -> Job Opening -> Job Requisition (Budgeted field, found by
label as in hr_custom.overrides.job_requisition).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, get_link_to_form, getdate, today

from hr_custom.overrides.job_requisition import get_fields, is_non_budgeted

APPROVED_STATUS = "Open & Approved"
# requisitions that no longer take a place in the plan
RELEASED_STATUSES = ("Rejected", "Cancelled")


def is_non_budgeted_requisition(job_requisition):
	if not job_requisition or not frappe.db.exists("Job Requisition", job_requisition):
		return False
	budgeted, _justification = get_fields(frappe.get_meta("Job Requisition"))
	if not budgeted:
		return False
	return is_non_budgeted(frappe.db.get_value("Job Requisition", job_requisition, budgeted.fieldname), budgeted.fieldtype)


def is_non_budgeted_opening(job_opening):
	return bool(job_opening) and is_non_budgeted_requisition(
		frappe.db.get_value("Job Opening", job_opening, "job_requisition")
	)


@frappe.whitelist()
def is_non_budgeted_hire(job_applicant=None, job_opening=None):
	"""True when the applicant's (or the given) Job Opening comes from a non-budgeted requisition.
	Server / Client Scripts doing their own staffing plan check can skip it when this is True:
	    if frappe.call("hr_custom.overrides.staffing_plan.is_non_budgeted_hire", job_applicant=doc.job_applicant): ...
	"""
	if not job_opening and job_applicant:
		job_opening = frappe.db.get_value("Job Applicant", job_applicant, "job_title")
	return is_non_budgeted_opening(job_opening)


class JobOpeningMixin:
	def validate_current_vacancies(self):
		if is_non_budgeted_requisition(self.get("job_requisition")):
			# HRMS would link the designation's active staffing plan and check its vacancies
			self.staffing_plan = None
			self.planned_vacancies = 0
			return
		return super().validate_current_vacancies()


class JobOfferMixin:
	def validate_vacancies(self):
		if is_non_budgeted_hire(self.job_applicant):
			return
		return super().validate_vacancies()


def is_approved(doc):
	return doc.get("status") == APPROVED_STATUS or "approved" in (doc.get("workflow_state") or "").lower()


def is_budgeted(doc):
	budgeted, _justification = get_fields(doc.meta)
	return bool(budgeted) and not is_non_budgeted(doc.get(budgeted.fieldname), budgeted.fieldtype)


def validate_requisition_staffing_plan(doc):
	"""Job Requisition validate: link and check the staffing plan of an approved budgeted requisition."""
	if not has_staffing_plan_link(doc.meta):
		return
	if not is_budgeted(doc):
		doc.staffing_plan = None
		return
	if not is_approved(doc) or doc.get("status") in RELEASED_STATUSES:
		return

	before = doc.get_doc_before_save()
	changed = not before or not is_approved(before) or not doc.staffing_plan or any(
		doc.get(f) != before.get(f) for f in ("designation", "company", "no_of_positions", "expected_compensation")
	)
	if changed:
		check_staffing_plan(doc)


def check_staffing_plan(doc):
	plan = get_staffing_plan_detail(doc.company, doc.designation, doc.get("posting_date") or today())
	if not plan:
		frappe.throw(
			_("No active Staffing Plan has {0} for {1}. Add it to the Staffing Plan, or set the requisition as not budgeted.").format(
				frappe.bold(doc.designation), frappe.bold(doc.company)
			),
			title=_("No Staffing Plan"),
		)

	taken = get_taken(plan.name, doc.designation, exclude=doc.name)
	positions = cint(doc.no_of_positions)
	cost_per_position = flt(doc.expected_compensation) or flt(plan.estimated_cost_per_position)
	cost = positions * cost_per_position
	vacancies_left = cint(plan.vacancies) - taken.positions
	budget_left = flt(plan.total_estimated_cost) - taken.cost
	currency = frappe.get_cached_value("Company", doc.company, "default_currency")

	if positions > vacancies_left:
		frappe.throw(
			_("Staffing Plan {0} has {1} vacancies for {2}; {3} are taken by other requisitions, so {4} are left and this requisition asks for {5}.").format(
				get_link_to_form("Staffing Plan", plan.name), cint(plan.vacancies), frappe.bold(doc.designation),
				taken.positions, frappe.bold(max(vacancies_left, 0)), frappe.bold(positions),
			),
			title=_("Staffing Plan Vacancies Exceeded"),
		)
	if flt(plan.total_estimated_cost) and cost > budget_left:
		frappe.throw(
			_("Staffing Plan {0} budget for {1} is {2}; {3} is taken by other requisitions, so {4} is left and this requisition costs {5} ({6} x {7}).").format(
				get_link_to_form("Staffing Plan", plan.name), frappe.bold(doc.designation),
				fmt_money(plan.total_estimated_cost, currency=currency), fmt_money(taken.cost, currency=currency),
				frappe.bold(fmt_money(max(budget_left, 0), currency=currency)), frappe.bold(fmt_money(cost, currency=currency)),
				positions, fmt_money(cost_per_position, currency=currency),
			),
			title=_("Staffing Plan Budget Exceeded"),
		)

	doc.staffing_plan = plan.name
	if doc.meta.has_field("staffing_plan_vacancies_left"):
		doc.staffing_plan_vacancies_left = vacancies_left - positions
	if doc.meta.has_field("staffing_plan_budget_left"):
		doc.staffing_plan_budget_left = budget_left - cost if flt(plan.total_estimated_cost) else 0


def get_staffing_plan_detail(company, designation, date):
	"""The designation's row of the submitted Staffing Plan covering `date` (company, else parent company)."""
	date = getdate(date)
	while company:
		sp = frappe.qb.DocType("Staffing Plan")
		spd = frappe.qb.DocType("Staffing Plan Detail")
		rows = (
			frappe.qb.from_(spd)
			.join(sp)
			.on(spd.parent == sp.name)
			.select(sp.name, spd.vacancies, spd.total_estimated_cost, spd.estimated_cost_per_position)
			.where(
				(sp.company == company)
				& (spd.designation == designation)
				& (sp.docstatus == 1)
				& (sp.from_date <= date)
				& (sp.to_date >= date)
			)
			.orderby(sp.from_date, order=frappe.qb.desc)
			.limit(1)
			.run(as_dict=True)
		)
		if rows:
			return rows[0]
		company = frappe.get_cached_value("Company", company, "parent_company")


def get_taken(staffing_plan, designation, exclude=None):
	"""Positions and cost of the other requisitions linked to the plan for the designation."""
	plan_cost = flt(
		frappe.db.get_value(
			"Staffing Plan Detail", {"parent": staffing_plan, "designation": designation}, "estimated_cost_per_position"
		)
	)
	positions, cost = 0, 0
	for d in frappe.get_all(
		"Job Requisition",
		filters={
			"staffing_plan": staffing_plan,
			"designation": designation,
			"name": ("!=", exclude or ""),
			"status": ("not in", RELEASED_STATUSES),
		},
		fields=["no_of_positions", "expected_compensation"],
	):
		positions += cint(d.no_of_positions)
		cost += cint(d.no_of_positions) * (flt(d.expected_compensation) or plan_cost)
	return frappe._dict(positions=positions, cost=cost)


def has_staffing_plan_link(meta):
	"""The requisition's Staffing Plan link (the site may already have its own `staffing_plan` field)."""
	df = meta.get_field("staffing_plan")
	return bool(df and df.fieldtype == "Link" and df.options == "Staffing Plan")


def make_fields():
	"""Staffing Plan, Plan Vacancies Left and Plan Budget Left on Job Requisition (fields the site
	already has are left as they are)."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	meta = frappe.get_meta("Job Requisition")
	existing = meta.get_field("staffing_plan")
	if existing:
		print(f"Job Requisition already has staffing_plan: {existing.fieldtype} {existing.options or ''} ({existing.label})")
		if not has_staffing_plan_link(meta):
			print("It is not a link to Staffing Plan: the requisition will not be linked to its plan.")

	fields = [
		{
			"fieldname": "staffing_plan",
			"fieldtype": "Link",
			"label": "Staffing Plan",
			"options": "Staffing Plan",
			"insert_after": "expected_compensation",
			"read_only": 1,
			"no_copy": 1,
			"description": "Linked when a budgeted requisition is approved",
		},
		{
			"fieldname": "staffing_plan_vacancies_left",
			"fieldtype": "Int",
			"label": "Plan Vacancies Left",
			"insert_after": "staffing_plan",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "staffing_plan",
		},
		{
			"fieldname": "staffing_plan_budget_left",
			"fieldtype": "Currency",
			"label": "Plan Budget Left",
			"options": "Company:company:default_currency",
			"insert_after": "staffing_plan_vacancies_left",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "staffing_plan",
		},
	]
	missing = [df for df in fields if not meta.has_field(df["fieldname"])]
	if missing:
		create_custom_fields({"Job Requisition": missing}, update=True)
	print("Added:", ", ".join(df["fieldname"] for df in missing) or "nothing (all fields exist)")
