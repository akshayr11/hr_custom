// 'Save Details from Offer': assign the offer's Leave Policy and Salary Structure to the employee
// created from the offer
frappe.ui.form.on("Job Offer", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.__onload || !frm.doc.__onload.employee) return;

		frm.add_custom_button(__("Save Details from Offer"), () => {
			frappe.call({
				method: "hr_custom.overrides.job_offer.get_offer_details",
				args: { job_offer: frm.doc.name },
				freeze: true,
				callback: (r) => r.message && confirm_save(frm, r.message),
			});
		});
	},
});

function confirm_save(frm, d) {
	const esc = frappe.utils.escape_html;
	const link = (doctype, name) =>
		`<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(name)}</a>`;
	const date = frappe.datetime.str_to_user;
	let todo = 0;

	let leave;
	if (d.existing_leave_policy_assignment) {
		const a = d.existing_leave_policy_assignment;
		leave = __("Already assigned: {0} ({1}, {2} to {3})", [
			link("Leave Policy Assignment", a.name),
			esc(a.leave_policy),
			date(a.effective_from),
			date(a.effective_to),
		]);
	} else if (d.leave_policy) {
		todo++;
		leave = __("Assign {0} from {1} and allocate its leaves", [
			`<b>${esc(d.leave_policy)}</b>`,
			date(d.date_of_joining),
		]);
	} else {
		leave = `<span class="text-danger">${__("No Leave Policy selected in the offer (Leave Cycle)")}</span>`;
	}

	let salary;
	if (d.existing_salary_structure_assignment) {
		const a = d.existing_salary_structure_assignment;
		salary = __("Already assigned: {0} ({1} from {2})", [
			link("Salary Structure Assignment", a.name),
			esc(a.salary_structure),
			date(a.from_date),
		]);
	} else if (d.components.length) {
		todo++;
		const rows = d.components
			.map(
				(c) => `<tr><td>${esc(c.salary_component)}</td>
					<td class="text-muted">${esc(c.source || "")}</td>
					<td class="text-right">${format_currency(c.amount)}</td></tr>`
			)
			.join("");
		const total = d.components.reduce((sum, c) => sum + c.amount, 0);
		salary = `${__("Create a Salary Structure with these earnings and assign it from {0} (Base: {1})", [
			date(d.date_of_joining),
			format_currency(d.basic),
		])}
			<table class="table table-bordered table-sm mt-2">
				<thead><tr><th>${__("Component")}</th><th>${__("From Offer Field")}</th>
					<th class="text-right">${__("Amount")}</th></tr></thead>
				<tbody>${rows}</tbody>
				<tfoot><tr><th colspan="2">${__("Total")}</th>
					<th class="text-right">${format_currency(total)}</th></tr></tfoot>
			</table>`;
	} else {
		salary = `<span class="text-danger">${__(
			"No salary amounts found in the offer that match an Earning Salary Component"
		)}</span>`;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Save Details from Offer"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__("Employee")}: ${link("Employee", d.employee)} ${esc(d.employee_name || "")}</p>
					<h5>${__("Leave Policy")}</h5><p>${leave}</p>
					<h5>${__("Salary Structure")}</h5><div>${salary}</div>`,
			},
		],
	});

	if (todo) {
		dialog.set_primary_action(__("Save"), () => {
			frappe.call({
				method: "hr_custom.overrides.job_offer.save_details_from_offer",
				args: { job_offer: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating..."),
				callback: (r) => {
					dialog.hide();
					const created = (r.message || []).map((c) => `${__(c.doctype)}: ${link(c.doctype, c.name)}`);
					frappe.msgprint({
						title: __("Saved"),
						indicator: "green",
						message: created.length ? created.join("<br>") : __("Nothing to create"),
					});
				},
			});
		});
	}
	dialog.show();
}
