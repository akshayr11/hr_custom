// Gratuity: recalculate (hr_custom rules) when the Till Date or Posting Date changes
frappe.ui.form.on("Gratuity", {
	gratuity_till_date(frm) {
		frm.events.calculate_work_experience_and_amount(frm);
	},
	posting_date(frm) {
		frm.events.calculate_work_experience_and_amount(frm);
	},
});
