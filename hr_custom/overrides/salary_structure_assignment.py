"""Airfare earning: every salary slip gets an "Airfare" earning of Employee's Yearly Airfare Cost / 12,
without adding the component to each Salary Structure.

HRMS evaluates a slip's structure components through the Salary Structure Assignment; the Airfare row
is appended there, so the slip treats it exactly like a structure component (formula, proration flag,
totals, accounting). Structures that already contain Airfare are left alone.
"""

import copy

import frappe
from frappe import _

AIRFARE_COMPONENT = "Airfare"
AIRFARE_ABBR = "AF"

# Salary Component settings carried onto the Airfare row
COMPONENT_FLAGS = (
	"depends_on_payment_days",
	"is_tax_applicable",
	"is_flexible_benefit",
	"variable_based_on_taxable_salary",
	"exempted_from_income_tax",
	"deduct_full_tax_on_selected_payroll_date",
	"statistical_component",
	"accrual_component",
	"do_not_include_in_total",
	"do_not_include_in_accounts",
)


class SalaryStructureAssignmentMixin:
	"""Newer HRMS (16.10+): slips get their structure components evaluated here."""

	def _evaluate_component_table(self, rows, data):
		if rows and rows[0].get("parentfield") == "earnings":
			rows = add_airfare_row(rows)
		return super()._evaluate_component_table(rows, data)


class SalarySlipMixin:
	"""Older HRMS (e.g. 16.4): the slip reads components straight from its Salary Structure. Give the
	slip a private copy of the structure with the Airfare row added (the cached structure is untouched).
	Newer HRMS has no set_salary_structure_doc, so this never runs there."""

	def set_salary_structure_doc(self):
		super().set_salary_structure_doc()
		earnings = list(self._salary_structure_doc.get("earnings") or [])
		with_airfare = add_airfare_row(earnings)
		if len(with_airfare) != len(earnings):
			structure = copy.copy(self._salary_structure_doc)
			structure.earnings = with_airfare
			self._salary_structure_doc = structure


def get_airfare_field():
	"""Employee's yearly airfare field, e.g. `custom_yearly_airfare_cost` (label 'Yearly Airfare Cost')."""
	fields = [
		df.fieldname
		for df in frappe.get_meta("Employee").fields
		if df.fieldtype in ("Currency", "Float") and "airfare" in df.fieldname.lower()
	]
	# prefer the yearly one if there are several
	return next((f for f in fields if "year" in f.lower()), fields[0] if fields else None)


def add_airfare_row(rows):
	if any(row.salary_component == AIRFARE_COMPONENT for row in rows):
		return rows

	fieldname = get_airfare_field()
	if not fieldname or not frappe.db.exists("Salary Component", AIRFARE_COMPONENT):
		return rows

	component = frappe.get_cached_doc("Salary Component", AIRFARE_COMPONENT)
	row = frappe.new_doc("Salary Detail")
	# own list (not imported from HRMS: older versions don't have one); copy what both doctypes have
	for field in COMPONENT_FLAGS:
		if component.meta.has_field(field) and row.meta.has_field(field):
			row.set(field, component.get(field))
	row.update(
		{
			"parentfield": "earnings",
			"parenttype": "Salary Structure",
			"salary_component": AIRFARE_COMPONENT,
			"abbr": component.salary_component_abbr or AIRFARE_ABBR,
			"amount_based_on_formula": 1,
			# skipped (no row on the slip) when the employee has no airfare
			"condition": f"{fieldname}",
			"formula": f"{fieldname} / 12",
		}
	)
	return [*rows, row]


def make_airfare_component():
	"""Create the Airfare earning component if missing (accounts must be set per company)."""
	if not frappe.db.exists("DocType", "Salary Component") or frappe.db.exists(
		"Salary Component", AIRFARE_COMPONENT
	):
		return

	fieldname = get_airfare_field()
	frappe.get_doc(
		{
			"doctype": "Salary Component",
			"salary_component": AIRFARE_COMPONENT,
			"salary_component_abbr": AIRFARE_ABBR,
			"type": "Earning",
			"depends_on_payment_days": 0,
			"remove_if_zero_valued": 1,
			"amount_based_on_formula": 1 if fieldname else 0,
			"formula": f"{fieldname} / 12" if fieldname else None,
			"description": _("Employee's Yearly Airfare Cost / 12, added to every salary slip by hr_custom"),
		}
	).insert(ignore_permissions=True)
