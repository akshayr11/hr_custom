// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

const WARNING_METHOD = "hr_custom.hr_custom.doctype.employee_warning.employee_warning";

frappe.ui.form.on("Employee Warning", {
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		frm.trigger("show_warning_history");

		if (frm.doc.docstatus === 0 && !frm.is_new() && frm.perm[1]?.write) {
			if (frm.doc.status === "Open") {
				frm.add_custom_button(__("Approve"), () => set_status_and_submit(frm, "Approved"));
				frm.add_custom_button(__("Reject"), () => set_status_and_submit(frm, "Rejected"));
			}
		}
	},

	employee(frm) {
		frm.trigger("show_warning_history");
		frm.trigger("calculate_deduction");
	},

	effective_date(frm) {
		frm.trigger("calculate_deduction");
	},

	action(frm) {
		if (frm.doc.action !== "Deduction") {
			frm.set_value({ no_of_days: 0, basic: 0, per_day_basic: 0, amount: 0 });
		}
		frm.trigger("calculate_deduction");
	},

	no_of_days(frm) {
		frm.trigger("calculate_deduction");
	},

	calculate_deduction(frm) {
		const d = frm.doc;
		if (d.action !== "Deduction" || !d.employee || !d.effective_date || !(d.no_of_days > 0)) return;

		frappe
			.xcall(`${WARNING_METHOD}.get_deduction_details`, {
				employee: d.employee,
				effective_date: d.effective_date,
				no_of_days: d.no_of_days,
				company: d.company,
			})
			.then((r) => frm.set_value(r));
	},

	show_warning_history(frm) {
		const wrapper = frm.get_field("warning_history_html").$wrapper;
		wrapper.empty();
		frm.set_intro("");
		if (!frm.doc.employee) return;

		frappe
			.xcall(`${WARNING_METHOD}.get_employee_warning_summary`, {
				employee: frm.doc.employee,
				exclude: frm.is_new() ? null : frm.doc.name,
			})
			.then((r) => {
				if (frm.doc.docstatus === 0) {
					frm.set_intro(
						r.history.length
							? __("This will be the {0} for {1} (previously warned {2} time(s)).", [
									`<b>${r.next_level}</b>`,
									frappe.utils.escape_html(frm.doc.employee_name || frm.doc.employee),
									r.history.length,
							  ])
							: __("This will be the <b>First Warning</b> for {0}.", [
									frappe.utils.escape_html(frm.doc.employee_name || frm.doc.employee),
							  ]),
						r.history.length ? "orange" : "blue"
					);
				}

				if (!r.history.length) {
					wrapper.html(`<p class="text-muted">${__("No previous warnings")}</p>`);
					return;
				}

				const rows = r.history
					.map(
						(w, i) => `<tr>
							<td>${i + 1}</td>
							<td><a href="/app/employee-warning/${encodeURIComponent(w.name)}">${w.name}</a></td>
							<td>${frappe.utils.escape_html(w.warning_type || "")}</td>
							<td>${frappe.datetime.str_to_user(w.effective_date)}</td>
							<td>${__(w.action || "")}</td>
							<td class="text-right">${w.action === "Deduction" ? w.no_of_days : ""}</td>
							<td class="text-right">${w.action === "Deduction" ? format_currency(w.amount) : ""}</td>
							<td>${frappe.utils.escape_html(w.reason || "")}</td>
						</tr>`
					)
					.join("");

				wrapper.html(`
					<table class="table table-bordered table-sm">
						<thead><tr>
							<th>#</th><th>${__("Warning")}</th><th>${__("Type")}</th>
							<th>${__("Effective Date")}</th><th>${__("Action")}</th>
							<th>${__("Days")}</th><th>${__("Amount")}</th><th>${__("Reason")}</th>
						</tr></thead>
						<tbody>${rows}</tbody>
					</table>`);
			});
	},
});

function set_status_and_submit(frm, status) {
	const message =
		status === "Approved" && frm.doc.action === "Deduction"
			? __("Approve this warning? A deduction of {0} will be added to payroll.", [
					format_currency(frm.doc.amount, frm.doc.currency),
			  ])
			: __("Mark this warning as {0} and submit?", [__(status)]);

	frappe.confirm(message, async () => {
		await frm.set_value("status", status);
		frm.save("Submit");
	});
}
