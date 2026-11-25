// partial payments: Make Payment while something is outstanding (HRMS's Create Journal Entry pays it all)
frappe.ui.form.on("Full and Final Statement", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !["Unpaid", "Partly Paid"].includes(frm.doc.status)) return;
		if (!(frm.doc.outstanding_amount > 0)) return;

		frm.add_custom_button(__("Make Payment"), () => {
			frappe.prompt(
				{
					fieldname: "amount",
					fieldtype: "Currency",
					label: __("Amount to Pay"),
					default: frm.doc.outstanding_amount,
					reqd: 1,
					description: __("Outstanding: {0}", [format_currency(frm.doc.outstanding_amount)]),
				},
				(values) => {
					frappe.call({
						method: "hr_custom.overrides.full_and_final_payment.make_payment",
						args: { statement: frm.doc.name, amount: values.amount },
						callback(r) {
							const doclist = frappe.model.sync(r.message);
							frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
						},
					});
				},
				__("Make Payment"),
				__("Create Journal Entry")
			);
		}).addClass("btn-primary");
	},
});
