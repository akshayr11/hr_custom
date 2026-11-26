# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeCTCSettings(Document):
	def validate(self):
		for row in self.costs:
			if row.based_on == "Salary Component" and not row.salary_component:
				frappe.throw(_("Row {0}: Salary Component is required").format(row.idx))
