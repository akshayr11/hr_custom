# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employees whose Passport / Visa / Civil ID / Driving License expires between two dates.

Passport and the driving license use fixed Employee fields; Civil ID and Visa are site custom
fields, so they are found by label ('Civil ID' / 'Visa No' with an expiry date labelled alike).
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate

from hr_custom.utils import EMPLOYEE_LOCATION_FIELD, has_employee_location

ID_TYPES = ("Passport", "Visa", "Civil ID", "Driving License")
NUMBER_TYPES = ("Data", "Small Text")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	id_types = ID_TYPES if filters.id_type in (None, "", "All") else (filters.id_type,)
	data = []
	for id_type in id_types:
		number_field, expiry_field = get_id_fields(id_type)
		if not expiry_field:
			if filters.id_type == id_type:
				frappe.throw(_("Employee has no expiry date field for {0}").format(_(id_type)))
			continue
		data += get_rows(filters, id_type, number_field, expiry_field)

	data.sort(key=lambda d: (d.expiry_date, d.employee))
	return get_columns(filters), data


def get_id_fields(id_type):
	"""(ID number field, expiry date field) on Employee."""
	meta = frappe.get_meta("Employee")

	def has(fieldname):
		return fieldname if meta.has_field(fieldname) else None

	if id_type == "Passport":
		return has("passport_number"), has("valid_upto")
	if id_type == "Driving License":
		return has("driving_license_no"), has("dl_expiry_date")
	if id_type == "Civil ID":
		number = find_field(meta, "civil", NUMBER_TYPES, exclude="expir")
		return number, has("civil_id_expiry_date") or find_field(meta, "civil", ("Date",))
	if id_type == "Visa":
		return find_field(meta, "visa", NUMBER_TYPES, exclude="expir"), find_field(meta, "visa", ("Date",), require="expir")
	return None, None


def find_field(meta, keyword, fieldtypes, exclude=None, require=None):
	for df in meta.fields:
		text = f"{df.fieldname} {df.label or ''}".lower()
		if (
			df.fieldtype in fieldtypes
			and keyword in text
			and (not exclude or exclude not in text)
			and (not require or require in text)
		):
			return df.fieldname


def get_rows(filters, id_type, number_field, expiry_field):
	emp = frappe.qb.DocType("Employee")
	query = (
		frappe.qb.from_(emp)
		.select(
			emp.name.as_("employee"),
			emp.employee_name,
			emp.department,
			emp.designation,
			emp[expiry_field].as_("expiry_date"),
		)
		.where(emp[expiry_field].between(getdate(filters.from_date), getdate(filters.to_date)))
		.orderby(emp[expiry_field])
	)
	if number_field:
		query = query.select(emp[number_field].as_("id_no"))
	location = EMPLOYEE_LOCATION_FIELD if has_employee_location() else "branch"
	query = query.select(emp[location].as_("location"))

	if filters.company:
		query = query.where(emp.company == filters.company)
	if filters.status:
		query = query.where(emp.status == filters.status)
	if filters.department:
		query = query.where(emp.department == filters.department)
	if filters.employee_category not in (None, "", "All") and frappe.get_meta("Employee").has_field(
		"employee_category"
	):
		query = query.where(emp.employee_category == filters.employee_category)

	today = nowdate()
	rows = query.run(as_dict=True)
	for d in rows:
		d.id_type = _(id_type)
		d.expires_within = date_diff(d.expiry_date, today)
	return rows


def get_columns(filters):
	columns = [
		{"fieldname": "employee", "label": _("Emp No"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 200},
	]
	if filters.id_type in (None, "", "All"):
		columns.append({"fieldname": "id_type", "label": _("ID Type"), "fieldtype": "Data", "width": 110})
	columns += [
		{"fieldname": "id_no", "label": _("ID No"), "fieldtype": "Data", "width": 140},
		{"fieldname": "expiry_date", "label": _("Exp Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "expires_within", "label": _("Expires Within (Days)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Data", "width": 130},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 160},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link", "options": "Designation", "width": 160},
	]
	return columns
