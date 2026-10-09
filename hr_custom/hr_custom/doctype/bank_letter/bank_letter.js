// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

const BANK_LETTER_MONTHS = [
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
];

const OT_TYPE_COLORS = { "With OT": "green", "Without OT": "orange", "OT Only": "blue" };

frappe.ui.form.on("Bank Letter", {
	setup(frm) {
		frm.set_query("cost_center", "cost_centers", () => ({
			filters: { company: frm.doc.company },
		}));
		frm.set_query("department", "departments", () => ({
			filters: { company: frm.doc.company },
		}));
		frm.set_query("employee", "selected_employees", () => ({
			filters: { company: frm.doc.company, status: "Active" },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.month) {
			const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
			frm.set_value("month", BANK_LETTER_MONTHS[today.getMonth()]);
			frm.set_value("year", today.getFullYear());
		}
	},

	refresh(frm) {
		frm.set_df_property("employees", "cannot_add_rows", true);
		frm.trigger("show_month_letters");

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Employees"), () => frm.trigger("get_employees")).addClass(
				"btn-primary"
			);
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("WPS Report"), () => frm.trigger("print_wps"), __("Print"));
			frm.add_custom_button(
				__("Bank Letter"),
				() => frm.trigger("print_letter"),
				__("Print")
			);
		}
	},

	on_submit(frm) {
		frm.trigger("print_wps");
	},

	// "WPS Report" is the default print format of Bank Letter
	print_wps(frm) {
		frm.print_doc();
	},

	print_letter(frm) {
		const params = new URLSearchParams({
			doctype: frm.doctype,
			name: frm.doc.name,
			format: "Bank Letter",
			no_letterhead: 0,
		});
		window.open(`/printview?${params}`, "_blank");
	},

	get_employees(frm) {
		frm.call({
			doc: frm.doc,
			method: "get_employees",
			freeze: true,
			freeze_message: __("Fetching employees..."),
			callback(r) {
				frm.refresh_fields();
				frm.dirty();
				if (!r.exc && !r.message) {
					frappe.msgprint(
						__(
							"No employees found. Either there are no submitted salary slips matching the filters, or the employees are already included in another Bank Letter for this month."
						)
					);
				}
			},
		});
	},

	company(frm) {
		frm.trigger("show_month_letters");
	},

	month(frm) {
		frm.trigger("show_month_letters");
	},

	year(frm) {
		frm.trigger("show_month_letters");
	},

	based_on(frm) {
		frm.set_value("cost_centers", []);
		frm.set_value("departments", []);
		frm.set_value("selected_employees", []);
		frm.set_value("head_office_selected", 0);
	},

	cost_centers(frm) {
		const cost_centers = (frm.doc.cost_centers || []).map((d) => d.cost_center).filter(Boolean);
		if (!cost_centers.length) {
			frm.set_value("head_office_selected", 0);
			frm.set_value("departments", []);
			return;
		}

		frappe.db
			.get_list("Cost Center", {
				filters: { name: ["in", cost_centers], is_head_office: 1 },
				limit: 1,
			})
			.then((rows) => {
				const is_head_office = rows.length ? 1 : 0;
				frm.set_value("head_office_selected", is_head_office);
				if (!is_head_office) frm.set_value("departments", []);
			});
	},

	// Show letters already made for the month so the user knows whether OT was paid
	show_month_letters(frm) {
		frm.dashboard.clear_headline();
		if (!frm.doc.company || !frm.doc.month || !frm.doc.year) return;

		frappe
			.xcall("hr_custom.hr_custom.doctype.bank_letter.bank_letter.get_month_letters", {
				company: frm.doc.company,
				month: frm.doc.month,
				year: frm.doc.year,
				exclude_letter: frm.is_new() ? null : frm.doc.name,
			})
			.then((letters) => {
				frm.dashboard.clear_headline();
				if (!letters.length) return;

				const items = letters
					.map((d) => {
						const status = d.docstatus === 1 ? __("Submitted") : __("Draft");
						return `<li>
							<a href="/app/bank-letter/${encodeURIComponent(d.name)}">${d.name}</a>
							&ndash; <span class="indicator-pill ${OT_TYPE_COLORS[d.ot_type] || "gray"}">${__(
							d.ot_type
						)}</span>
							&ndash; ${frappe.utils.escape_html(d.bank || "")}, ${d.total_employees} ${__(
							"employees"
						)}, ${format_currency(d.total_amount)} (${status})
						</li>`;
					})
					.join("");

				frm.dashboard.set_headline_alert(
					`<div>${__("Bank Letters already created for {0} {1}:", [
						__(frm.doc.month),
						frm.doc.year,
					])}</div><ul class="mb-0">${items}</ul>`,
					"yellow"
				);
			});
	},
});

