// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

// Service Request belongs to another app; field names are read from the doctype's meta.

frappe.ui.form.on("Service Request", {
	setup(frm) {
		const company_field = sr_link_fields(frm, "Company")[0];
		if (!company_field) return;

		const cost_center_fields = sr_link_fields(frm, "Cost Center");
		for (const field of cost_center_fields) {
			frm.set_query(field, () => ({
				filters: { company: frm.doc[company_field], is_group: 0 },
			}));
		}

		// clear cost centers of another company when Company changes (register once)
		if (!frappe.flags.sr_company_handler) {
			frappe.flags.sr_company_handler = true;
			frappe.ui.form.on("Service Request", company_field, (form) => {
				for (const field of cost_center_fields) form.set_value(field, "");
			});
		}
	},

	// Reject / Close through the workflow: ask for the remarks first
	before_workflow_action(frm) {
		const next_state = sr_next_state(frm, frm.selected_workflow_action).toLowerCase();
		const action = (frm.selected_workflow_action || "").toLowerCase();
		const is_reject = next_state.includes("reject") || action.includes("reject");
		const is_close = !is_reject && (next_state.includes("close") || action.includes("close"));
		if (!is_reject && !is_close) return;

		const fieldname = sr_remarks_field(frm, is_reject ? "reject" : "closure");
		if (!fieldname || (frm.doc[fieldname] || "").trim()) return;

		frappe.dom.unfreeze();
		const label = __(frappe.meta.get_label(frm.doctype, fieldname));
		return new Promise((resolve) => {
			frappe.prompt(
				{ fieldname: "remarks", fieldtype: "Small Text", label, reqd: 1 },
				(values) => {
					frm.doc[fieldname] = values.remarks;
					frm.refresh_field(fieldname);
					frappe.dom.freeze();
					resolve();
				},
				is_reject ? __("Reject Request") : __("Close Request"),
				is_reject ? __("Reject") : __("Close")
			);
		});
	},
});

function sr_link_fields(frm, options) {
	return frm.meta.fields
		.filter((df) => df.fieldtype === "Link" && df.options === options)
		.map((df) => df.fieldname);
}

function sr_remarks_field(frm, keyword) {
	const text_types = ["Small Text", "Text", "Long Text", "Text Editor", "Data"];
	const df = frm.meta.fields.find((d) => text_types.includes(d.fieldtype) && d.fieldname.includes(keyword));
	return df && df.fieldname;
}

function sr_next_state(frm, action) {
	const workflow = frappe.workflow.workflows[frm.doctype];
	if (!workflow) return "";
	const state = frm.doc[workflow.workflow_state_field];
	const transition = (workflow.transitions || []).find((t) => t.state === state && t.action === action);
	return (transition && transition.next_state) || "";
}
