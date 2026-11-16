# Copyright (c) 2026, akshayr11 and contributors
# For license information, please see license.txt

"""Employee Checkin Upload: the punches exported from the attendance machine become Employee
Checkins (HRMS links each to the employee's shift), then the shifts' Auto Attendance is run so
the attendance is marked (late entry / early exit as per the shift) and linked to the check-ins.

HRMS gives a check-in a shift only when it is within the shift's check-in / check-out window
(Begin Check-in Before Shift Start / Allow Check-out After Shift End); a punch outside it (e.g.
a check-out 2 hours after the shift end) gets the employee's nearest shift here instead, so it
is still the check-in / check-out of that shift's attendance. A punch of a shift whose attendance
is already marked (e.g. the check-out uploaded in a later file, or a day Auto Attendance marked
Absent before its check-ins were uploaded) updates that attendance.

File: one row per punch - Employee (ID, Attendance Device ID or full name), Time (date and
time, or separate Date and Time columns) and an optional Log Type (IN / OUT).
"""

import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now_datetime

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
SHIFT_FIELDS = ("shift", "shift_start", "shift_end", "shift_actual_start", "shift_actual_end", "offshift", "overtime_type")
CHECKIN_FIELDS = ["name", "employee", "log_type", "time", "shift", "shift_start", "shift_end", "device_id"]
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
		log, created, duplicates, errors = [], [], 0, 0
		seen, without_shift = set(), []

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
			if not checkin.shift:
				without_shift.append(checkin.name)

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

		log += assign_shifts(without_shift)
		if created and cint(self.mark_attendance):
			frappe.db.commit()
			log += mark_attendance(self.name)

		self.upload_log = "\n".join(log)
		self.save(ignore_permissions=True)
		frappe.msgprint(
			_("{0} check-ins created, {1} already uploaded, {2} rows with errors").format(
				self.created_checkins, self.duplicate_rows, self.error_rows
			),
			alert=True,
		)

	@frappe.whitelist()
	def fetch_shift_and_mark_attendance(self):
		"""For check-ins uploaded before the shift setup was right: fetch the shift of this upload's
		check-ins that have no attendance yet, then mark / update the attendance."""
		names = frappe.get_all(
			"Employee Checkin", filters={"device_id": self.name, "attendance": ("is", "not set")}, pluck="name"
		)
		if not names:
			frappe.msgprint(_("All check-ins of this upload are already linked to attendance"))
			return
		# skipped by HRMS when the attendance already existed; they are added to it now
		frappe.db.set_value("Employee Checkin", {"name": ("in", names)}, "skip_auto_attendance", 0, update_modified=False)
		log = assign_shifts(names, refetch=True)
		frappe.db.commit()
		log += mark_attendance(self.name)
		self.db_set("upload_log", "\n".join(filter(None, [self.upload_log, *log])))
		frappe.msgprint("<br>".join(log) or _("Done"), title=_("Fetch Shift and Mark Attendance"))

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


def assign_shifts(names, refetch=False):
	"""Shift of the check-ins (HRMS's, else the nearest one); returns log lines."""
	from hrms.hr.doctype.shift_assignment.shift_assignment import get_employee_shift_timings

	missing = 0
	for name in names:
		doc = frappe.get_doc("Employee Checkin", name)
		if refetch:
			try:
				doc.fetch_shift()
			except frappe.ValidationError:  # e.g. Log Type required by the shift
				frappe.clear_messages()
		if not doc.shift:
			time = get_datetime(doc.time)
			shifts = [s for s in get_employee_shift_timings(doc.employee, time, True) if s]
			if not shifts:
				missing += 1
				continue
			shift = min(shifts, key=lambda s: distance(s, time))
			doc.update(
				{
					"shift": shift.shift_type.name,
					"shift_start": shift.start_datetime,
					"shift_end": shift.end_datetime,
					"shift_actual_start": min(shift.actual_start, time),
					"shift_actual_end": max(shift.actual_end, time),
					"offshift": 0,
					"overtime_type": shift.overtime_type or None,
				}
			)
		frappe.db.set_value("Employee Checkin", name, {f: doc.get(f) for f in SHIFT_FIELDS}, update_modified=False)

	if missing:
		return [_("{0} check-ins have no shift: set the employee's Default Shift or a Shift Assignment").format(missing)]
	return []


def distance(shift, time):
	"""Time between the punch and the shift's start - end."""
	if time < shift.start_datetime:
		return shift.start_datetime - time
	if time > shift.end_datetime:
		return time - shift.end_datetime
	return datetime.timedelta(0)


def mark_attendance(upload):
	"""Add the upload's check-ins to the attendance already marked for their shift, then run the
	Auto Attendance of the shifts up to now; returns log lines."""
	log = add_to_marked_attendance(upload)
	shifts = frappe.get_all(
		"Employee Checkin",
		filters={"device_id": upload, "attendance": ("is", "not set"), "shift": ("is", "set")},
		pluck="shift",
		distinct=True,
	)
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


def add_to_marked_attendance(upload):
	"""Check-ins of a shift whose attendance is already marked - from other check-ins (e.g. the
	check-out uploaded later), or Absent by Auto Attendance as the day had no check-ins yet:
	recalculate that attendance's status, in / out time, hours, late entry / early exit."""
	from hr_custom.overrides.attendance import get_attendance_code, get_deduction_minutes

	logs = frappe.get_all(
		"Employee Checkin",
		filters={"device_id": upload, "attendance": ("is", "not set"), "shift": ("is", "set"), "skip_auto_attendance": 0},
		fields=CHECKIN_FIELDS,
		order_by="employee, time",
	)
	groups = {}
	for d in logs:
		groups.setdefault((d.employee, d.shift, get_datetime(d.shift_start)), []).append(d)

	updated = 0
	for (employee, shift_name, shift_start), new_logs in groups.items():
		attendance = frappe.db.get_value(
			"Attendance",
			{"employee": employee, "attendance_date": shift_start.date(), "docstatus": 1},
			["name", "status", "in_time", "leave_type", "attendance_request"],
			as_dict=True,
		)
		if not attendance:  # Auto Attendance marks it
			continue
		name = attendance.name
		linked = frappe.get_all("Employee Checkin", filters={"attendance": name}, fields=CHECKIN_FIELDS, order_by="time")
		# marked Absent by Auto Attendance as there were no check-ins yet
		auto_absent = (
			attendance.status == "Absent"
			and not (attendance.in_time or attendance.leave_type or attendance.attendance_request)
		)
		if not (linked or auto_absent):  # marked by hand / leave: left as it is
			continue

		shift = frappe.get_cached_doc("Shift Type", shift_name)
		all_logs = sorted(linked + new_logs, key=lambda d: get_datetime(d.time))
		for d in all_logs:  # the new logs' shift start / end (the nearest shift's) for all
			d.shift_start, d.shift_end = new_logs[0].shift_start, new_logs[0].shift_end
		status, hours, late_entry, early_exit, in_time, out_time = shift.get_attendance(
			all_logs, flt(shift.working_hours_threshold_for_absent), flt(shift.working_hours_threshold_for_half_day)
		)
		attendance = frappe.get_doc("Attendance", name)
		values = {
			"shift": shift_name,
			"working_hours": hours,
			"late_entry": late_entry,
			"early_exit": early_exit,
			"in_time": in_time,
			"out_time": out_time,
		}
		if attendance.status in ("Present", "Absent", "Half Day"):
			values["status"] = status
		attendance.update(values)
		values.update(attendance_code=get_attendance_code(attendance), **get_deduction_minutes(attendance))
		attendance.db_set(values)
		frappe.db.set_value("Employee Checkin", {"name": ("in", [d.name for d in new_logs])}, "attendance", name, update_modified=False)
		updated += 1

	return [_("{0} attendance records updated with the new check-ins").format(updated)] if updated else []


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
