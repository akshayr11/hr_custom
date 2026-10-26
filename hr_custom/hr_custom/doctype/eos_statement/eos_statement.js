// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.ui.form.on("EOS Statement", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print EOS"), () => frm.print_doc()).addClass("btn-primary");
			frm.set_intro(
				frm.doc.eligible
					? __("Gratuity up to {0}: {1}", [
							frappe.datetime.str_to_user(frm.doc.till_date),
							format_currency(frm.doc.total_gratuity, frm.doc.currency),
					  ])
					: __("Not eligible for gratuity: {0}", [frm.doc.eligibility_remarks]),
				frm.doc.eligible ? "green" : "orange"
			);
		}
	},
});
