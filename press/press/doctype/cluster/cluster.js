// Copyright (c) 2021, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cluster', {
	refresh: function (frm) {
		[
			[__('Prepare VPC'), 'prepare_vpc', frm.doc.status === 'Active'],
			[__('Create Servers'), 'create_servers', frm.doc.status === 'Active'],
			[__('Add Images'), 'add_images', frm.doc.status === 'Active'],
		].forEach(([label, method, condition]) => {
			if (typeof condition === 'undefined' || condition) {
				frm.add_custom_button(
					label,
					() => {
						frappe.confirm(
							`Are you sure you want to ${label.toLowerCase()}?`,
							() =>
								frm.call(method).then((r) => {
									if (r.message) {
										frappe.msgprint(r.message);
									} else {
										frm.refresh();
									}
								}),
						);
					},
					__('Actions'),
				);
			}
		});
		if (frm.doc.vpc_id) {
			if (frm.doc.cloud_provider === 'AWS EC2') {
				frm.add_web_link(
					`https://${frm.doc.region}.console.aws.amazon.com/vpc/home?region=${frm.doc.region}#VpcDetails:VpcId=${frm.doc.vpc_id}`,
					__('Visit AWS Dashboard'),
				);
			} else if (frm.doc.cloud_provider === 'OCI') {
				frm.add_web_link(
					`https://cloud.oracle.com/networking/vcns/${frm.doc.vpc_id}?region=${frm.doc.region}`,
					__('Visit OCI Dashboard'),
				);
			}
		}
	},
});
