# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Date


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "transfer_no", "label": _("Transfer No"), "fieldtype": "Link", "options": "Tool Transfer", "width": 150},
		{"fieldname": "transfer_date", "label": _("Transfer Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "tool_no", "label": _("Tool No"), "fieldtype": "Link", "options": "Tool Registry", "width": 120},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "source_location", "label": _("Source Location"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "target_location", "label": _("Target Location"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "from_crew", "label": _("From Crew"), "fieldtype": "Data", "width": 110},
		{"fieldname": "to_crew", "label": _("To Crew"), "fieldtype": "Data", "width": 110},
		{"fieldname": "from_employee", "label": _("From Employee"), "fieldtype": "Link", "options": "Employee", "width": 125},
		{"fieldname": "to_employee", "label": _("To Employee"), "fieldtype": "Link", "options": "Employee", "width": 125},
		{"fieldname": "from_asset", "label": _("From Asset"), "fieldtype": "Link", "options": "Asset", "width": 125},
		{"fieldname": "to_asset", "label": _("To Asset"), "fieldtype": "Link", "options": "Asset", "width": 125},
	]


def get_data(filters):
	tt = frappe.qb.DocType("Tool Transfer")
	row = frappe.qb.DocType("Tool Transfer Child Table")
	tr = frappe.qb.DocType("Tool Registry")
	item = frappe.qb.DocType("Item")
	transfer_date = Date(tt.transaction_date)

	query = (
		frappe.qb.from_(tt)
		.join(row)
		.on((row.parent == tt.name) & (row.parenttype == "Tool Transfer"))
		.left_join(tr)
		.on(row.tool_no == tr.name)
		.left_join(item)
		.on(tr.item_code == item.name)
		.select(
			tt.name.as_("transfer_no"),
			transfer_date.as_("transfer_date"),
			row.tool_no,
			tr.item_code,
			item.item_name,
			row.source_location,
			row.target_location,
			row.from_crew,
			row.target_crew.as_("to_crew"),
			row.from_employee,
			row.to_employee,
			row.from_asset,
			row.to_asset,
		)
		.where(tt.docstatus == 1)
		.orderby(tt.transaction_date)
		.orderby(tt.name)
		.orderby(row.idx)
	)

	if filters.get("from_date"):
		query = query.where(transfer_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(transfer_date <= filters.to_date)
	if filters.get("company"):
		query = query.where(tt.company == filters.company)
	if filters.get("tool_no"):
		query = query.where(row.tool_no == filters.tool_no)
	if filters.get("item_code"):
		query = query.where(tr.item_code == filters.item_code)
	if filters.get("location"):
		query = query.where((row.source_location == filters.location) | (row.target_location == filters.location))
	if filters.get("employee"):
		query = query.where((row.from_employee == filters.employee) | (row.to_employee == filters.employee))

	return query.run(as_dict=True)
