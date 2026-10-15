# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "stock_issue_no", "label": _("Stk Issue No"), "fieldtype": "Link", "options": "Stock Entry", "width": 150},
		{"fieldname": "stock_issue_date", "label": _("Stk Issue Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "tool_no", "label": _("Tool No"), "fieldtype": "Link", "options": "Tool Registry", "width": 120},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Emp Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "asset_no", "label": _("Asset No"), "fieldtype": "Link", "options": "Asset", "width": 130},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "tool_specification", "label": _("Tool Specification"), "fieldtype": "Data", "width": 160},
		{"fieldname": "serial_no", "label": _("Serial No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "make", "label": _("Make"), "fieldtype": "Data", "width": 110},
		{"fieldname": "model", "label": _("Model"), "fieldtype": "Data", "width": 110},
		{"fieldname": "certificate_no", "label": _("Certificate No"), "fieldtype": "Data", "width": 130},
		{"fieldname": "certificate_expiry_date", "label": _("Certificate Expiry Date"), "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	tr = frappe.qb.DocType("Tool Registry")
	item = frappe.qb.DocType("Item")
	emp = frappe.qb.DocType("Employee")
	asset = frappe.qb.DocType("Asset")
	se = frappe.qb.DocType("Stock Entry")

	query = (
		frappe.qb.from_(tr)
		.left_join(item)
		.on(tr.item_code == item.name)
		.left_join(emp)
		.on(tr.custodian_employee_no == emp.name)
		.left_join(asset)
		.on(tr.asset_no == asset.name)
		.left_join(se)
		.on(tr.stock_issue_no == se.name)
		.select(
			tr.stock_issue_no,
			se.posting_date.as_("stock_issue_date"),
			tr.name.as_("tool_no"),
			tr.item_code,
			item.item_name,
			tr.custodian_employee_no.as_("employee"),
			emp.employee_name,
			tr.asset_no,
			asset.asset_name,
			tr.location,
			tr.tool_specification,
			tr.serial_no,
			tr.make,
			tr.model,
			tr.certificate_no,
			tr.certificate_expiry_date,
		)
		.orderby(tr.name)
	)

	for field, column in (
		("location", tr.location),
		("employee", tr.custodian_employee_no),
		("item_code", tr.item_code),
		("asset_no", tr.asset_no),
		("tool_status", tr.tool_status),
	):
		if filters.get(field):
			query = query.where(column == filters.get(field))

	if filters.get("from_date"):
		query = query.where(se.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(se.posting_date <= filters.to_date)

	return query.run(as_dict=True)
