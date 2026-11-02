// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Rejoining", {
	setup(frm) {
		frm.set_query("leave_application", () => ({
			filters: {
				employee: frm.doc.employee,
				docstatus: 1,
				status: "Approved",
				leave_type: ["in", frm._annual_leave_types || []],
			},
		}));
	},

	refresh(frm) {
		load_defaults(frm);
		if (frm.doc.docstatus === 0 && frm.doc.rejoin_status && frm.doc.rejoin_status !== "On Time") {
			frm.set_intro(
				frm.doc.rejoin_status === "Late"
					? __("{0} day(s) will be deducted as {1} when this is approved.", [
							frm.doc.leave_days_to_adjust,
							frm.doc.extra_days_leave_type,
					  ])
					: __("{0} unused leave day(s) will be added back to the {1} balance when this is approved.", [
							frm.doc.leave_days_to_adjust,
							frm.doc.leave_type,
					  ]),
				"orange"
			);
		}
	},

	employee(frm) {
		frm.set_value("leave_application", null);
		load_defaults(frm, true);
	},

	leave_application(frm) {
		calculate(frm);
	},

	rejoin_date(frm) {
		calculate(frm);
	},

	extra_days_leave_type(frm) {
		calculate(frm);
	},
});

function load_defaults(frm, set_leave) {
	if (!frm.doc.employee) return;
	frappe.call({
		method: "hr_custom.overrides.rejoin_date.get_rejoining_defaults",
		args: { employee: frm.doc.employee },
		callback(r) {
			frm._annual_leave_types = r.message.leave_types;
			if (set_leave && r.message.leave_application) {
				frm.set_value("leave_application", r.message.leave_application);
			}
		},
	});
}

// expected date, days late / early and the leave days to adjust, shown before saving
function calculate(frm) {
	if (!frm.doc.leave_application || !frm.doc.rejoin_date || frm.doc.docstatus !== 0) return;
	frm.call({ doc: frm.doc, method: "set_rejoin_details" }).then(() => frm.refresh());
}
