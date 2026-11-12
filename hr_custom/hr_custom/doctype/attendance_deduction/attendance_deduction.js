// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Deduction", {
	setup(frm) {
		frm.set_query("salary_component", () => ({ filters: { type: "Deduction" } }));
		frm.set_query("payroll_cost_center", () => ({ filters: { company: frm.doc.company } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.from_date) {
			// previous month
			const start = moment().subtract(1, "month").startOf("month");
			frm.set_value("from_date", start.format("YYYY-MM-DD"));
			frm.set_value("to_date", start.clone().endOf("month").format("YYYY-MM-DD"));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Employees"), () => {
				if (!frm.doc.company || !frm.doc.from_date || !frm.doc.to_date) {
					frappe.msgprint(__("Please set Company, From Date and To Date"));
					return;
				}
				frm.call({ doc: frm.doc, method: "get_employees", freeze: true }).then(() => frm.refresh());
			}).addClass("btn-primary");
		}
	},

	to_date(frm) {
		if (frm.doc.to_date && !frm.doc.payroll_date) {
			frm.set_value("payroll_date", frm.doc.to_date);
		}
	},

	deduction_divisor(frm) {
		calculate(frm);
	},
});

frappe.ui.form.on("Attendance Deduction Employee", {
	approved_minutes(frm, cdt, cdn) {
		calculate(frm);
	},
});

function calculate(frm) {
	const divisor = flt(frm.doc.deduction_divisor);
	let minutes = 0;
	let amount = 0;
	(frm.doc.employees || []).forEach((row) => {
		row.deduction_amount = divisor ? flt((flt(row.total_salary) * cint(row.approved_minutes)) / divisor, 3) : 0;
		minutes += cint(row.approved_minutes);
		amount += row.deduction_amount;
	});
	frm.set_value({ total_approved_minutes: minutes, total_deduction_amount: amount });
	frm.refresh_field("employees");
}
