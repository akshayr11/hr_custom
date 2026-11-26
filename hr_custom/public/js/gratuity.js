// Gratuity: recalculate (hr_custom rules) when the Till Date or Posting Date changes;
// Net Gratuity Payable = Amount - Prepaid Gratuity (worked out again on save)
frappe.ui.form.on("Gratuity", {
	gratuity_till_date(frm) {
		frm.events.calculate_work_experience_and_amount(frm);
	},
	posting_date(frm) {
		frm.events.calculate_work_experience_and_amount(frm);
	},
	amount(frm) {
		if (frm.doc.docstatus === 0 && frm.fields_dict.net_gratuity_payable) {
			frm.set_value(
				"net_gratuity_payable",
				Math.max(flt(frm.doc.amount) - flt(frm.doc.total_prepaid_gratuity), 0)
			);
		}
	},
});
