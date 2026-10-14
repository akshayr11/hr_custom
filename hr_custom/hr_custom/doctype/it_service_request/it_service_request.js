// Copyright (c) 2026, akshayr11 and contributors
// For license information, please see license.txt

const ITSR_METHOD = "hr_custom.hr_custom.doctype.it_service_request.it_service_request";

// status -> button label
const ITSR_ACTIONS = {
	"Pending for Submission": __("Send for Submission"),
	Draft: __("Back to Draft"),
	Received: __("Mark Received"),
	"In Progress": __("Start Work"),
	Completed: __("Mark Completed"),
	Closed: __("Close"),
	Reopened: __("Reopen"),
};

// fields the requester fills; locked while Pending for Submission
const ITSR_REQUEST_FIELDS = [
	"employee",
	"request_type",
	"request_date",
	"contact_no",
	"email",
	"system_type",
	"system_code",
	"brand_model",
	"problem_type",
	"erp_module",
	"description",
];

frappe.ui.form.on("IT Service Request", {
	setup(frm) {
		// masters can be disabled instead of deleted
		for (const field of ["request_type", "system_type", "problem_type", "erp_module"]) {
			frm.set_query(field, () => ({ filters: { disabled: 0 } }));
		}
	},

	onload(frm) {
		// requester's own employee record by default
		if (frm.is_new() && !frm.doc.employee) {
			frappe
				.xcall(`${ITSR_METHOD}.get_employee_for_user`)
				.then((employee) => employee && frm.set_value("employee", employee));
		}
	},

	refresh(frm) {
		const pending = frm.doc.status === "Pending for Submission";
		for (const field of ITSR_REQUEST_FIELDS) {
			frm.set_df_property(field, "read_only", pending ? 1 : 0);
		}

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.set_intro(
				pending
					? __("Check the details and click Submit to send this request to IT, or Back to Draft to edit.")
					: __("Click 'Send for Submission' when the request is ready."),
				"blue"
			);
		} else {
			frm.set_intro("");
		}

		if (!frm.is_new() && frm.doc.docstatus < 2) add_status_buttons(frm);
	},

	requires_erp_module(frm) {
		if (!frm.doc.requires_erp_module) frm.set_value("erp_module", "");
	},
});

function add_status_buttons(frm) {
	frappe.xcall(`${ITSR_METHOD}.get_status_actions`, { name: frm.doc.name }).then((statuses) => {
		for (const status of statuses) {
			const button = frm.add_custom_button(ITSR_ACTIONS[status] || __(status), () =>
				change_status(frm, status)
			);
			if (["Pending for Submission", "Received", "In Progress", "Completed", "Closed"].includes(status)) {
				button.addClass("btn-primary");
			}
		}
	});
}

function change_status(frm, status) {
	const run = (reason) =>
		frappe
			.xcall(`${ITSR_METHOD}.change_status`, { name: frm.doc.name, status, reason })
			.then(() => frm.reload_doc());

	const go = () => (frm.is_dirty() ? frm.save().then(() => run()) : run());

	if (status === "Reopened") {
		frappe.prompt(
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason for reopening"), reqd: 1 },
			(values) => run(values.reason),
			__("Reopen Request"),
			__("Reopen")
		);
	} else if (status === "Closed") {
		frappe.confirm(__("Close this request? It cannot be reopened after closing."), go);
	} else {
		go();
	}
}
