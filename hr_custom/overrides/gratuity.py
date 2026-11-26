"""HRMS Gratuity: amount calculated with the company's rules (see EOS Statement) instead of the
Gratuity Rule slabs - Expats only, more than 1 year, half basic for the first 3 years for employees
who joined on or before 31-Jul-2023, Freeze Basic up to its Till Date.

The gratuity is calculated up to Till Date, else the employee's Relieving Date, else Posting Date.

Prepaid Gratuity: the salary slips that already paid gratuity through payroll (components ticked
"Is Prepaid Gratuity", see hr_custom.overrides.full_and_final) are listed on a draft Gratuity,
with Prepaid Amount and Net Gratuity Payable = Amount - Prepaid. The Amount stays the full
gratuity; the Full and Final Statement deducts the prepaid part from it.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hr_custom.hr_custom.doctype.eos_statement.eos_statement import DAYS_IN_YEAR, get_gratuity

GRATUITY_RULE = "Oman Expat Gratuity"


class GratuityMixin:
	def validate(self):
		super().validate()
		if self.docstatus == 0:
			self.set_prepaid_gratuity()

	def set_prepaid_gratuity(self):
		from hr_custom.overrides.full_and_final import get_gratuity_instalments

		if not self.meta.has_field("prepaid_gratuity"):
			return
		self.set("prepaid_gratuity", get_gratuity_instalments(self.employee))
		self.total_prepaid_gratuity = flt(sum(flt(d.amount) for d in self.prepaid_gratuity))
		self.net_gratuity_payable = max(flt(self.amount) - self.total_prepaid_gratuity, 0)
		if self.total_prepaid_gratuity > flt(self.amount) and flt(self.amount):
			frappe.msgprint(
				_("Prepaid Gratuity {0} is more than the Gratuity {1}").format(
					frappe.format(self.total_prepaid_gratuity, "Currency"), frappe.format(self.amount, "Currency")
				),
				indicator="orange",
				alert=True,
			)

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
					"fieldname": "total_prepaid_gratuity",
					"fieldtype": "Currency",
					"label": "Prepaid Gratuity Amount",
					"options": "Company:company:default_currency",
					"insert_after": "amount",
					"read_only": 1,
					"no_copy": 1,
					"description": "Already paid through payroll (Prepaid Gratuity component)",
				},
				{
					"fieldname": "net_gratuity_payable",
					"fieldtype": "Currency",
					"label": "Net Gratuity Payable",
					"options": "Company:company:default_currency",
					"insert_after": "total_prepaid_gratuity",
					"read_only": 1,
					"no_copy": 1,
					"bold": 1,
					"description": "Amount - Prepaid Gratuity; deducted in the Full and Final Statement",
				},
				{
					"fieldname": "prepaid_gratuity_section",
					"fieldtype": "Section Break",
					"label": "Prepaid Gratuity (Paid through Payroll)",
					"insert_after": "gratuity_details",
					"depends_on": "eval:doc.total_prepaid_gratuity",
				},
				{
					"fieldname": "prepaid_gratuity",
					"fieldtype": "Table",
					"label": "Prepaid Gratuity",
					"options": "Full and Final Gratuity Instalment",
					"insert_after": "prepaid_gratuity_section",
					"read_only": 1,
					"no_copy": 1,
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
