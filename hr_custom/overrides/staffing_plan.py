"""Non-budgeted hiring: no Staffing Plan.

A Job Requisition with Budgeted = No is hired for outside the staffing plan, so its Job Opening
is not linked to (or checked against) a Staffing Plan, and the Job Offers for its applicants are
not checked against staffing plan vacancies / budget.

Path: Job Offer -> Job Applicant -> Job Opening -> Job Requisition (Budgeted field, found by
label as in hr_custom.overrides.job_requisition).
"""

import frappe

from hr_custom.overrides.job_requisition import get_fields, is_non_budgeted


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
