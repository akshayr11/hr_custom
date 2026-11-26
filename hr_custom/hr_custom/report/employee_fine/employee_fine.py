# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee Fine: the Employee Fines (oerp_custom) of a period - employee, equipment, fine type,
date and amount."""

import frappe
from frappe import _

STATUS_DOCSTATUS = {"Submitted": [1], "Draft": [0], "Draft and Submitted": [0, 1]}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not frappe.db.exists("DocType", "Employee Fines"):
		frappe.throw(_("Employee Fines is not installed on this site"))
	return get_columns(), get_data(filters)


def get_columns():
	def col(label, fieldname, fieldtype="Data", width=130, **kw):
		return {"label": _(label), "fieldname": fieldname, "fieldtype": fieldtype, "width": width, **kw}

	return [
		col("Emp No", "employee", "Link", 120, options="Employee"),
		col("Employee Name", "employee_name", width=180),
		col("Equipment", "equipment", "Link", 140, options="Item"),
		col("Equipment Name", "equipment_name", width=170),
		col("Reg No", "reg_no", width=110),
		col("Fine Type", "fine_type", "Link", 150, options="Fine Type Master"),
		col("Date", "fine_date", "Date", 100),
		col("Amount", "amount", "Currency", 110),
		col("Remarks", "remarks", width=200),
		col("Fine No", "name", "Link", 190, options="Employee Fines"),
	]


def get_data(filters):
	fine = frappe.qb.DocType("Employee Fines")
	emp = frappe.qb.DocType("Employee")
	meta = frappe.get_meta("Employee Fines")

	query = (
		frappe.qb.from_(fine)
		.left_join(emp)
		.on(fine.employee == emp.name)
		.select(
			fine.name,
			fine.employee,
			fine.employee_name,
			fine.equipment,
			fine.fine_type,
			fine.fine_date,
			fine.amount,
		)
		.where(fine.docstatus.isin(STATUS_DOCSTATUS.get(filters.status or "Submitted", [1])))
		.orderby(fine.fine_date)
		.orderby(fine.employee)
	)
	for field in ("equipment_name", "reg_no", "remarks"):
		if meta.has_field(field):
			query = query.select(fine[field])

	if filters.from_date:
		query = query.where(fine.fine_date >= filters.from_date)
	if filters.to_date:
		query = query.where(fine.fine_date <= filters.to_date)
	for field in ("employee", "equipment", "fine_type"):
		if filters.get(field):
			query = query.where(fine[field] == filters.get(field))
	if filters.company:
		query = query.where(emp.company == filters.company)
	if filters.department:
		query = query.where(emp.department == filters.department)

	return query.run(as_dict=True)
