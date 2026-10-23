// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

frappe.ui.form.on("Salary Slip Download", {
	setup(frm) {
		frm.set_query("print_format", () => ({ filters: { doc_type: "Salary Slip", disabled: 0 } }));
		frm.set_query("employees", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("department", () => ({ filters: { company: frm.doc.company } }));
	},

	onload(frm) {
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		const month = MONTH_NAMES[today.getMonth()];
		frm.doc.company ||= frappe.defaults.get_user_default("Company");
		frm.doc.from_month ||= month;
		frm.doc.to_month ||= month;
		frm.doc.from_year ||= today.getFullYear();
		frm.doc.to_year ||= today.getFullYear();
		frm.doc.print_format ||= "Employee Payslip";
		frm.refresh_fields();
	},

	refresh(frm) {
		frm.disable_save();
		frm.page.set_primary_action(__("Download PDF"), () => frm.trigger("download"), "printer");
	},

	download(frm) {
		const missing = ["company", "from_month", "from_year", "to_month", "to_year", "print_format"].filter(
			(f) => !frm.doc[f]
		);
		if (missing.length) {
			frappe.msgprint(
				__("Please set {0}", [missing.map((f) => __(frm.fields_dict[f].df.label)).join(", ")])
			);
			return;
		}

		frappe
			.xcall("hr_custom.hr_custom.doctype.salary_slip_download.salary_slip_download.get_salary_slips", {
				filters: {
					company: frm.doc.company,
					employees: (frm.doc.employees || []).map((d) => d.employee),
					department: frm.doc.department,
					from_month: frm.doc.from_month,
					from_year: frm.doc.from_year,
					to_month: frm.doc.to_month,
					to_year: frm.doc.to_year,
					include_draft: frm.doc.include_draft,
				},
			})
			.then((names) => {
				if (!names.length) {
					frappe.msgprint(__("No salary slips found for these filters."));
					return;
				}
				frappe.show_alert({ message: __("Downloading {0} salary slip(s)...", [names.length]), indicator: "blue" });
				// POST, so a long list of slips does not hit the URL length limit
				open_url_post(
					"/api/method/frappe.utils.print_format.download_multi_pdf",
					{
						doctype: "Salary Slip",
						name: JSON.stringify(names),
						format: frm.doc.print_format,
						no_letterhead: frm.doc.letter_head ? 0 : 1,
						letterhead: frm.doc.letter_head || "",
					},
					true
				);
			});
	},
});

const MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];
