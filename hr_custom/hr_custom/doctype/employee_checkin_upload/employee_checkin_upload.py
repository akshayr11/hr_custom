# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee Checkin Upload: the punches exported from the attendance machine become Employee
Checkins (HRMS links each to the employee's shift), then the shifts' Auto Attendance is run so
the attendance is marked (late entry / early exit as per the shift) and linked to the check-ins.

File: one row per punch - Employee (ID, Attendance Device ID or full name), Time (date and
time, or separate Date and Time columns) and an optional Log Type (IN / OUT).
"""

import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, get_datetime, getdate, now_datetime

# punches processed in the request; bigger files run in the background
SYNC_LIMIT = 300
TEMPLATE_COLUMNS = ["Employee", "Time", "Log Type"]
HEADERS = {
	"employee": "employee",
	"employee id": "employee",
	"employee no": "employee",
	"emp no": "employee",
	"emp id": "employee",
	"empno": "employee",
	"employee code": "employee",
	"emp code": "employee",
	"attendance device id": "employee",
	"device id": "employee",
	"biometric id": "employee",
	"user id": "employee",
	"time": "time",
	"date time": "time",
	"datetime": "time",
	"date/time": "time",
	"punch time": "time",
	"log time": "time",
	"check-in time": "time",
	"checkin time": "time",
	"date": "date",
	"punch date": "date",
	"log type": "log_type",
	"type": "log_type",
	"in/out": "log_type",
	"direction": "log_type",
}
LOG_TYPES = {"in": "IN", "i": "IN", "check in": "IN", "checkin": "IN", "out": "OUT", "o": "OUT", "check out": "OUT", "checkout": "OUT"}


class EmployeeCheckinUpload(Document):
	@frappe.whitelist()
	def upload(self):
		if self.status == "Uploaded":
			frappe.throw(_("This file is already uploaded"))
		rows = self.read_rows()
		if len(rows) > SYNC_LIMIT:
			self.db_set("status", "Queued")
			frappe.enqueue_doc(self.doctype, self.name, "process", queue="long", timeout=3600)
			frappe.msgprint(_("{0} rows are being uploaded in the background. Reload in a few minutes.").format(len(rows)))
			return
		self.process()

	def process(self):
		rows = self.read_rows()
		employees = EmployeeMatcher(self.company)
		log, created, duplicates, errors, shifts = [], [], 0, 0, set()
		seen = set()

		for row_no, row in rows:
			try:
				employee = employees.find(row.get("employee"))
				time = get_punch_time(row)
				log_type = LOG_TYPES.get(cstr(row.get("log_type")).strip().lower())
			except frappe.ValidationError as e:
				errors += 1
				log.append(_("Row {0}: {1}").format(row_no, e))
				frappe.clear_messages()
				continue

			if (employee, time) in seen or frappe.db.exists("Employee Checkin", {"employee": employee, "time": time}):
				duplicates += 1
				continue
			seen.add((employee, time))

			try:
				checkin = frappe.get_doc(
					{
						"doctype": "Employee Checkin",
						"employee": employee,
						"time": time,
						"log_type": log_type,
						"device_id": self.name,
					}
				)
				checkin.flags.ignore_permissions = True
				checkin.insert()
			except Exception as e:
				errors += 1
				log.append(_("Row {0}: {1}").format(row_no, cstr(e)))
				frappe.clear_messages()
				continue
			created.append(time)
			if checkin.shift:
				shifts.add(checkin.shift)

		self.total_rows = len(rows)
		self.created_checkins = len(created)
		self.duplicate_rows = duplicates
		self.error_rows = errors
		self.from_time = min(created) if created else None
		self.to_time = max(created) if created else None
		if errors:
			self.status = "Partly Uploaded" if created else "Failed"
		else:
			self.status = "Uploaded"

		if created and cint(self.mark_attendance):
			frappe.db.commit()
			log += mark_attendance(shifts)

		self.upload_log = "\n".join(log)
		self.save(ignore_permissions=True)
		frappe.msgprint(
			_("{0} check-ins created, {1} already uploaded, {2} rows with errors").format(
				self.created_checkins, self.duplicate_rows, self.error_rows
			),
			alert=True,
		)

	def read_rows(self):
		"""[(row number in the file, {employee, time, date, log_type})]"""
		sheet = read_sheet(self.checkin_file)
		for idx, values in enumerate(sheet[:10]):
			columns = {i: HEADERS[label] for i, value in enumerate(values) if (label := cstr(value).strip().lower()) in HEADERS}
			if "employee" in columns.values() and ("time" in columns.values() or "date" in columns.values()):
				break
		else:
			frappe.throw(_("The file needs the columns {0}").format(", ".join(TEMPLATE_COLUMNS)))

		rows = []
		for row_no, values in enumerate(sheet[idx + 1 :], start=idx + 2):
			row = {field: values[i] for i, field in columns.items() if i < len(values)}
			if any(cstr(v).strip() for v in row.values()):
				rows.append((row_no, row))
		if not rows:
			frappe.throw(_("No check-ins found in the file"))
		return rows


class EmployeeMatcher:
	"""Employee from the file's ID: Employee ID, Attendance Device ID, or a unique full name."""

	def __init__(self, company):
		self.by_id, self.by_device, by_name = {}, {}, {}
		for d in frappe.get_all(
			"Employee",
			filters={"company": company} if company else {},
			fields=["name", "attendance_device_id", "employee_name"],
		):
			self.by_id[d.name.lower()] = d.name
			if d.attendance_device_id:
				self.by_device[cstr(d.attendance_device_id).strip().lower()] = d.name
			by_name.setdefault((d.employee_name or "").strip().lower(), []).append(d.name)
		self.by_name = {name: matches[0] for name, matches in by_name.items() if len(matches) == 1}

	def find(self, value):
		key = cstr(value).strip()
		if isinstance(value, float) and value.is_integer():  # device IDs read as numbers from Excel
			key = str(int(value))
		key = key.lower()
		if not key:
			frappe.throw(_("Employee is missing"))
		employee = self.by_id.get(key) or self.by_device.get(key) or self.by_name.get(key)
		if not employee:
			frappe.throw(_("Employee {0} not found").format(frappe.bold(cstr(value))))
		return employee


def get_punch_time(row):
	time, date = row.get("time"), row.get("date")
	if date not in (None, ""):
		date = getdate(date)
		if isinstance(time, datetime.datetime):
			time = time.time()
		elif isinstance(time, float | int):  # Excel time: fraction of a day
			time = (datetime.datetime.min + datetime.timedelta(days=float(time) % 1)).time()
		elif time not in (None, ""):
			time = get_datetime(f"2000-01-01 {cstr(time).strip()}").time()
		else:
			frappe.throw(_("Time is missing"))
		return datetime.datetime.combine(date, time.replace(microsecond=0))

	if time in (None, ""):
		frappe.throw(_("Time is missing"))
	value = time if isinstance(time, datetime.datetime) else get_datetime(cstr(time).strip())
	if not value or value.year < 2000:
		frappe.throw(_("{0} is not a date and time").format(cstr(time)))
	return value.replace(microsecond=0)


def mark_attendance(shifts):
	"""Run Auto Attendance of the shifts up to now; returns log lines."""
	log = []
	for name in sorted(shifts):
		shift = frappe.get_doc("Shift Type", name)
		if not (cint(shift.enable_auto_attendance) and shift.process_attendance_after):
			log.append(
				_("Shift {0}: attendance not marked - tick Enable Auto Attendance and set Process Attendance After").format(name)
			)
			continue
		if not shift.last_sync_of_checkin or get_datetime(shift.last_sync_of_checkin) < now_datetime():
			shift.db_set("last_sync_of_checkin", now_datetime(), update_modified=False)
		try:
			shift.process_auto_attendance()
			log.append(_("Shift {0}: attendance marked").format(name))
		except Exception:
			frappe.db.rollback()
			log.append(_("Shift {0}: attendance marking failed, see Error Log").format(name))
			frappe.log_error(title=f"Employee Checkin Upload: Auto Attendance of {name}")
	return log


def read_sheet(file_url):
	file = frappe.get_doc("File", {"file_url": file_url})
	extension = (file.file_name or file_url).rsplit(".", 1)[-1].lower()
	if extension == "xlsx":
		from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

		return read_xlsx_file_from_attached_file(fcontent=file.get_content())
	if extension == "csv":
		from frappe.utils.csvutils import read_csv_content

		return read_csv_content(file.get_content())
	frappe.throw(_("Upload the check-ins as an Excel (.xlsx) or CSV file."))


@frappe.whitelist()
def download_template():
	from frappe.utils.xlsxutils import make_xlsx

	sample = ["HR-EMP-00001", "2026-10-01 07:58:00", "IN"]
	xlsx = make_xlsx([TEMPLATE_COLUMNS, sample], "Check-ins")
	frappe.response["filename"] = "employee_checkin_template.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
