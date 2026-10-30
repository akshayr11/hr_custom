// alert as soon as a backdated / already-processed Promotion Date is chosen
frappe.ui.form.on("Employee Promotion", {
	promotion_date(frm) {
		check_promotion_date(frm);
	},
	employee(frm) {
		check_promotion_date(frm);
	},
});

function check_promotion_date(frm) {
	if (!frm.doc.employee || !frm.doc.promotion_date) return;
	frappe.call({
		method: "hr_custom.overrides.employee_promotion.get_promotion_date_warnings",
		args: { employee: frm.doc.employee, promotion_date: frm.doc.promotion_date },
		callback: (r) => {
			if (!r.message || !r.message.length) return;
			frappe.msgprint({
				title: __("Check Promotion Date"),
				indicator: "orange",
				message:
					r.message.join("<br><br>") +
					"<br><br>" +
					__("Please change the Promotion Date if this is not intended."),
			});
		},
	});
}
