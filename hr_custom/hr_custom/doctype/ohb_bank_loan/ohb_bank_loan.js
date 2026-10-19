// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

const OHB_LOAN_METHOD = "hr_custom.hr_custom.doctype.ohb_bank_loan.ohb_bank_loan";

frappe.ui.form.on("OHB Bank Loan", {
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.bank) {
			// same loan bank as the last loan entered
			frappe.db
				.get_list("OHB Bank Loan", { fields: ["bank"], order_by: "creation desc", limit: 1 })
				.then((r) => r.length && !frm.doc.bank && frm.set_value("bank", r[0].bank));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.perm[0]?.write) {
			const [label, status] =
				frm.doc.status === "Active" ? [__("Inactivate"), "Inactive"] : [__("Activate"), "Active"];
			frm.add_custom_button(label, () => {
				frm.set_value("status", status);
				frm.save("Update");
			});
		}

		if (frm.doc.docstatus === 1 && frm.doc.balance_amount <= 0) {
			frm.set_intro(__("Loan fully paid: Bank Letters no longer deduct an installment."), "blue");
		} else if (frm.doc.docstatus === 1) {
			frm.set_intro(
				frm.doc.status === "Active"
					? __("Installment of {0} is deducted from the salary in Bank Letters and transferred to the OHB account until the balance of {1} is paid.", [
							format_currency(frm.doc.monthly_installment, frm.doc.currency),
							format_currency(frm.doc.balance_amount, frm.doc.currency),
					  ])
					: __("Loan is Inactive: Bank Letters pay the full salary to the employee's account."),
				frm.doc.status === "Active" ? "green" : "orange"
			);
		}
	},

	employee(frm) {
		if (!frm.doc.employee) return;
		frappe
			.xcall(`${OHB_LOAN_METHOD}.get_employee_details`, { employee: frm.doc.employee })
			.then((r) => frm.set_value(r));
	},

	total_loan_amount(frm) {
		frm.set_value("balance_amount", flt(frm.doc.total_loan_amount) - flt(frm.doc.paid_amount));
	},
});
