<template>
	<PlansCards v-model="currentPlan" :plans="plans" />
</template>

<script>
import PlansCards from './PlansCards.vue';
import { getPlans } from '../data/plans';

export default {
	name: 'SitePlansCards',
	props: [
		'modelValue',
		'isPrivateBenchSite',
		'isDedicatedServerSite',
		'selectedCluster',
		'selectedApps',
		'selectedVersion',
		'hideRestrictedPlans',
		'selectedEnvironment'
	],
	emits: ['update:modelValue'],
	components: {
		PlansCards
	},
	computed: {
		currentPlan: {
			get() {
				return this.modelValue;
			},
			set(value) {
				this.$emit('update:modelValue', value);
			}
		},
		plans() {
			let plans = getPlans();

			if (this.isPrivateBenchSite) {
				plans = plans.filter(plan => plan.private_benches);
			}
			if (this.isPrivateBenchSite && this.isDedicatedServerSite) {
				plans = plans.filter(plan => plan.dedicated_server_plan);
			} else {
				plans = plans.filter(plan => !plan.dedicated_server_plan);
			}
			if (this.selectedCluster) {
				plans = plans.map(plan => {
					return {
						...plan,
						disabled:
							plan.disabled ||
							(plan.clusters.length == 0
								? false
								: !plan.clusters.includes(this.selectedCluster))
					};
				});
			}
			if (this.selectedApps) {
				plans = plans.map(plan => {
					return {
						...plan,
						disabled:
							plan.disabled ||
							(plan.allowed_apps.length == 0
								? false
								: !this.selectedApps.every(app =>
										plan.allowed_apps.includes(app.app)
								  ))
					};
				});
			}
			if (this.selectedVersion) {
				plans = plans.map(plan => {
					return {
						...plan,
						disabled:
							plan.disabled ||
							(plan.bench_versions.length == 0
								? false
								: !plan.bench_versions.includes(this.selectedVersion))
					};
				});
			}
			if (this.hideRestrictedPlans) {
				plans = plans.filter(plan => !plan.restricted_plan);
			}
			if (this.selectedEnvironment == 'Development') {
				plans = plans.filter(plan => plan.cpu_time_per_day < 24);
			} else {
				plans = plans.filter(plan => plan.cpu_time_per_day == 24);
			}
			if (this.selectedCluster == 'New Client' && this.selectedEnvironment !== 'Demo') {
				plans = plans.filter(plan => plan.max_database_usage > 0);
			}
			else {
				plans = plans.filter(plan => plan.max_database_usage == 0);
				if (this.selectedEnvironment == 'Demo') {
					plans = plans.filter(plan => plan.vcpu == 2 && plan.memory == 1024);
				}
			}

			return plans.map(plan => {
				return {
					...plan,
					features: [
						{
							label: `${this.$format.plural(
								plan.cpu_time_per_day,
								'compute hour',
								'compute hours'
							)} / day`,
							condition: !plan.name.includes('Unlimited'),
							value: plan.cpu_time_per_day
						},
						{
							label: 'Processing',
							condition: !plan.name.includes('Unlimited'),
							value: `${plan.vcpu} vCPUs`
						},
						{
							label: 'Memory',
							condition: !plan.name.includes('Unlimited'),
							value: this.$format.bytes(plan.memory, 0, 2)
						},
						{
							label: 'Storage',
							condition: !plan.name.includes('Unlimited'),
							value: `${this.$format.bytes(plan.max_storage_usage + plan.max_database_usage, 0, 2)} SSD`
						},
						{
							value: plan.support_included ? 'Product Warranty' : ''
						},
						{
							value: plan.database_access ? 'Database Access' : ''
						},
						{
							value: plan.offsite_backups ? 'Offsite Backups' : ''
						},
						{
							value: plan.monitor_access ? 'Advanced Monitoring' : ''
						}
					].filter(feature => feature.condition ?? true)
				};
			});
		}
	}
};
</script>
