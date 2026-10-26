"""HRMS Gratuity: amount calculated with the company's rules (see EOS Statement) instead of the
Gratuity Rule slabs - Expats only, more than 1 year, half basic for the first 3 years for employees
who joined on or before 31-Jul-2023, Freeze Basic up to its Till Date.

The gratuity is calculated up to Till Date, else the employee's Relieving Date, else Posting Date.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hr_custom.hr_custom.doctype.eos_statement.eos_statement import DAYS_IN_YEAR, get_gratuity

GRATUITY_RULE = "Oman Expat Gratuity"


class GratuityMixin:
	@frappe.whitelist()
	def calculate_work_experience_and_amount(self) -> dict:
		if not self.employee:
			return {"current_work_experience": 0, "amount": 0}

		till_date = self.get_till_date()
		result = get_gratuity(self.employee, till_date)
		self.update(
			{
				"gratuity_till_date": till_date,
				"eligibility_remarks": result["eligibility_remarks"],
				"calculation_basis": result.get("calculation_basis"),
			}
		)
		self.set("gratuity_details", result["details"])

		return {
			"current_work_experience": flt(result["service_days"] / DAYS_IN_YEAR, 2),
			"amount": result["total_gratuity"],
		}

	def get_till_date(self):
		return (
			self.get("gratuity_till_date")
			or frappe.db.get_value("Employee", self.employee, "relieving_date")
			or self.posting_date
		)

	def before_submit(self):
		if not flt(self.amount):
			frappe.throw(
				_("Employee is not eligible for gratuity: {0}").format(self.get("eligibility_remarks") or ""),
				title=_("Not Eligible"),
			)


def make_fields():
	"""Till Date and calculation breakdown on Gratuity, and a default Gratuity Rule (mandatory)."""
	if not frappe.db.exists("DocType", "Gratuity"):
		return

	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	create_custom_fields(
		{
			"Gratuity": [
				{
					"fieldname": "gratuity_till_date",
					"fieldtype": "Date",
					"label": "Till Date",
					"insert_after": "posting_date",
					"description": "Gratuity is calculated up to this date. Empty: the employee's Relieving Date, else Posting Date.",
				},
				{
					"fieldname": "gratuity_calculation_section",
					"fieldtype": "Section Break",
					"label": "Gratuity Calculation",
					"insert_after": "amended_from",
				},
				{
					"fieldname": "eligibility_remarks",
					"fieldtype": "Small Text",
					"label": "Eligibility",
					"insert_after": "gratuity_calculation_section",
					"read_only": 1,
				},
				{
					"fieldname": "gratuity_calculation_column",
					"fieldtype": "Column Break",
					"insert_after": "eligibility_remarks",
				},
				{
					"fieldname": "calculation_basis",
					"fieldtype": "Small Text",
					"label": "Calculation Basis",
					"insert_after": "gratuity_calculation_column",
					"read_only": 1,
				},
				{
					"fieldname": "gratuity_details_section",
					"fieldtype": "Section Break",
					"insert_after": "calculation_basis",
				},
				{
					"fieldname": "gratuity_details",
					"fieldtype": "Table",
					"label": "Gratuity Details",
					"options": "EOS Gratuity Detail",
					"insert_after": "gratuity_details_section",
					"read_only": 1,
				},
			]
		},
		update=True,
	)

	if not frappe.db.exists("Gratuity Rule", GRATUITY_RULE):
		rule = frappe.get_doc(
			{
				"doctype": "Gratuity Rule",
				"name": GRATUITY_RULE,
				"work_experience_calculation_function": "Manual",
				"calculate_gratuity_amount_based_on": "Current Slab",
				"total_working_days_per_year": 365,
				"minimum_year_for_gratuity": 1,
				"description": "Calculated by hr_custom: Expats only, more than 1 year of service, half basic for the "
				"first 3 years if joined on or before 31-Jul-2023, Freeze Basic up to its Till Date.",
				"gratuity_rule_slabs": [{"from_year": 0, "to_year": 0, "fraction_of_applicable_earnings": 1}],
			}
		)
		rule.flags.ignore_mandatory = True
		rule.insert(ignore_permissions=True)

	make_property_setter("Gratuity", "gratuity_rule", "default", GRATUITY_RULE, "Text", validate_fields_for_doctype=False)
