import { createListResource } from 'frappe-ui';
import { defineAsyncComponent, h, reactive } from 'vue';
import { renderDialog } from '../../utils/components';
import type {
	BannerConfig,
	ColumnField,
	DocumentResource,
	Route,
	Row
} from './types';
import { trialDays } from '../../utils/site';
import { planTitle } from '../../utils/format';

export const unreachable = Error('unreachable'); // used to indicate that a codepath is unreachable

export const clusterOptions: string[] = reactive(['']);

createListResource({
	doctype: 'Cluster',
	fields: ['name', 'title'],
	orderBy: 'title asc',
	auto: true,
	onSuccess(data: { name: string }[]) {
		clusterOptions.splice(0, clusterOptions.length, '', ...data.map(c => c.name));
	}
});

export function getUpsellBanner(site: DocumentResource, title: string) {
	if (
		!site.doc.current_plan ||
		site.doc.current_plan?.private_benches ||
		site.doc.current_plan?.is_trial_plan ||
		!site.doc.group_public
	)
		return;

	return {
		title: title,
		dismissable: true,
		id: site.name,
		button: {
			label: 'Upgrade Plan',
			variant: 'outline',
			onClick() {
				let SitePlansDialog = defineAsyncComponent(
					() => import('../../components/ManageSitePlansDialog.vue')
				);
				renderDialog(h(SitePlansDialog, { site: site.name }));
			}
		}
	} satisfies BannerConfig as BannerConfig;
}

export function getSitesTabColumns(forBenchTab: boolean) {
	return [
		{
			label: 'Site',
			fieldname: 'host_name',
			format(value, row) {
				return value || row.name;
			},
			prefix: () => {
				if (forBenchTab) return;
				return h('div', { class: 'ml-2 w-3.5 h-3.5' });
			}
		},
		{
			label: 'Status',
			fieldname: 'status',
			type: 'Badge',
			width: 0.5
		},
		{
			label: 'Project',
			fieldname: 'cluster_title',
			width: 0.5,
			prefix(row) {
				if (row.cluster_title)
					return h('img', {
						src: row.cluster_image,
						class: 'w-4 h-4',
						alt: row.cluster_title
					});
			}
		},
		{
			label: 'Plan',
			width: 0.5,
			format(value, row) {
				if (row.trial_end_date) {
					return trialDays(row.trial_end_date);
				}
				return planTitle(row);
			}
		}
	] satisfies ColumnField[] as ColumnField[];
}

export function siteTabFilterControls() {
	return [
		{
			type: 'select',
			label: 'Status',
			fieldname: 'status',
			options: ['', 'Active', 'Inactive', 'Suspended', 'Broken']
		},
		{
			type: 'select',
			label: 'Project',
			fieldname: 'cluster',
			options: clusterOptions
		}
	];
}

export function sitesTabRoute(r: Row) {
	return {
		name: 'Site Detail',
		params: { name: r.name }
	} satisfies Route as Route;
}
