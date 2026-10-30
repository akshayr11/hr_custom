// Advance Salary (reviewed) schedules: editable while in Draft, then Activated (submitted)
const EDITABLE_FIELDS = ["payment_date", "principal_amount"];

frappe.ui.form.on("Loan Repayment Schedule", {
	refresh(frm) {
		const review = frm.doc.docstatus === 0 && frm.doc.__onload && frm.doc.__onload.review_schedule;
		const grid = frm.fields_dict.repayment_schedule.grid;

		frm.set_df_property("repayment_schedule", "read_only", review ? 0 : 1);
		EDITABLE_FIELDS.forEach((f) => grid.update_docfield_property(f, "read_only", review ? 0 : 1));
		grid.refresh();
		if (!review) return;

		frm.set_intro(
			__(
				"Review the schedule: change dates or amounts, or set a month to 0 (or delete it) to skip it. The principal must add up to {0}. Save, then click Activate to start the repayments.",
				[format_currency(frm.doc.current_principal_amount || frm.doc.disbursed_amount)]
			),
			"orange"
		);
		frm.add_custom_button(__("Activate"), () => {
			frappe.confirm(__("Activate this repayment schedule? It cannot be edited afterwards."), () =>
				frm.savesubmit()
			);
		}).addClass("btn-primary");
	},
});

frappe.ui.form.on("Repayment Schedule", {
	principal_amount(frm) {
		show_difference(frm);
	},
	repayment_schedule_remove(frm) {
		show_difference(frm);
	},
});

function show_difference(frm) {
	const total = (frm.doc.repayment_schedule || []).reduce((sum, d) => sum + flt(d.principal_amount), 0);
	const diff = flt(frm.doc.current_principal_amount || frm.doc.disbursed_amount) - total;
	if (Math.abs(diff) >= 0.005) {
		frappe.show_alert({
			message: __("Principal total {0}, still to schedule {1}", [
				format_currency(total),
				format_currency(diff),
			]),
			indicator: "orange",
		});
	}
}
