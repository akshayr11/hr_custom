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
		// Table MultiSelect fields take the query on the field itself, not via a grid
		frm.set_query("cost_centers", () => ({
			filters: { company: frm.doc.company },
		}));
		frm.set_query("departments", () => ({
			filters: { company: frm.doc.company },
		}));
		frm.set_query("selected_employees", () => ({
			filters: { company: frm.doc.company },
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
				if (!r.exc && r.message && !r.message.count) {
					frappe.msgprint({
						title: __("No employees found"),
						indicator: "orange",
						message: r.message.reason || __("No employees match the filters."),
					});
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
		frm.set_value({
			cost_centers: [],
			departments: [],
			selected_employees: [],
			all_cost_centers: 0,
			all_departments: 0,
			head_office_selected: 0,
		});
	},

	all_cost_centers(frm) {
		if (frm.doc.all_cost_centers) frm.set_value("cost_centers", []);
		frm.trigger("cost_centers");
	},

	all_departments(frm) {
		if (frm.doc.all_departments) frm.set_value("departments", []);
	},

	// Departments are needed when a Head Office cost center is part of the selection
	cost_centers(frm) {
		const cost_centers = (frm.doc.cost_centers || []).map((d) => d.cost_center).filter(Boolean);
		if (!frm.doc.all_cost_centers && !cost_centers.length) {
			set_head_office_selected(frm, 0);
			return;
		}

		const filters = { is_head_office: 1, company: frm.doc.company };
		if (!frm.doc.all_cost_centers) filters.name = ["in", cost_centers];

		frappe.db
			.get_list("Cost Center", { filters, limit: 1 })
			.then((rows) => set_head_office_selected(frm, rows.length ? 1 : 0));
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


function set_head_office_selected(frm, value) {
	frm.set_value("head_office_selected", value);
	if (!value) frm.set_value({ departments: [], all_departments: 0 });
}
