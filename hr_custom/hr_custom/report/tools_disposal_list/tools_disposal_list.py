# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, NullIf


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "transaction_no", "label": _("Transaction No"), "fieldtype": "Link", "options": "Tools Disposal", "width": 150},
		{"fieldname": "disposal_date", "label": _("Disposal Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "reference_no", "label": _("Ref No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "tool_no", "label": _("Tool No"), "fieldtype": "Link", "options": "Tool Registry", "width": 120},
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 250},
	]


def get_data(filters):
	td = frappe.qb.DocType("Tools Disposal")
	row = frappe.qb.DocType("Tools Disposal Item")
	tr = frappe.qb.DocType("Tool Registry")
	item = frappe.qb.DocType("Item")
	item_code = Coalesce(NullIf(row.item_code, ""), tr.item_code)

	query = (
		frappe.qb.from_(td)
		.join(row)
		.on((row.parent == td.name) & (row.parenttype == "Tools Disposal"))
		.left_join(tr)
		.on(row.tool_no == tr.name)
		.left_join(item)
		.on(item_code == item.name)
		.select(
			td.name.as_("transaction_no"),
			td.disposal_date,
			td.reference_no,
			row.tool_no,
			item_code.as_("item_code"),
			item.item_name,
			row.location,
			# reason per tool, else the disposal's remarks
			Coalesce(NullIf(row.disposal_reason, ""), td.remarks).as_("reason"),
		)
		.where(td.docstatus == 1)
		.orderby(td.disposal_date)
		.orderby(td.name)
		.orderby(row.idx)
	)

	if filters.get("from_date"):
		query = query.where(td.disposal_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(td.disposal_date <= filters.to_date)
	if filters.get("location"):
		query = query.where(row.location == filters.location)
	if filters.get("item_code"):
		query = query.where(item_code == filters.item_code)
	if filters.get("tool_no"):
		query = query.where(row.tool_no == filters.tool_no)

	return query.run(as_dict=True)
