<!-- dashboard/src2/components/site/SiteScheduleCard.vue -->
<template>
	<div class="rounded-md border">
		<div class="flex h-12 items-center justify-between border-b px-5">
			<h2 class="text-lg font-medium text-gray-900">Instance Schedule</h2>
			<div class="flex items-center space-x-2">
				<template v-if="schedule">
					<Button
						:variant="schedule.enabled ? 'solid' : 'outline'"
						size="sm"
						@click="toggleEnabled"
						:loading="$site.setSchedule.loading || $site.disableSchedule.loading"
					>
						{{ schedule.enabled ? 'Enabled' : 'Disabled' }}
					</Button>
					<Dropdown v-if="$team?.doc?.is_desk_user" :options="menuOptions">
						<Button variant="ghost" icon="more-horizontal" />
					</Dropdown>
				</template>
				<Button v-else variant="outline" size="sm" @click="showSetScheduleDialog">
					Set Schedule
				</Button>
			</div>
		</div>
		<div class="px-5 py-4">
			<template v-if="!schedule">
				<p class="text-sm text-gray-500">No schedule configured. Site runs 24/7.</p>
			</template>
			<template v-else>
				<div class="flex items-start justify-between">
					<div>
						<p class="font-medium text-gray-900">{{ schedule.preset }}</p>
						<p class="mt-0.5 text-sm text-gray-500">{{ presetSummary }}</p>
					</div>
					<Dropdown
						v-if="schedule.enabled && schedule.override === 'None'"
						:options="overrideOptions"
					>
						<Button variant="outline" size="sm">
							Override
							<template #suffix>
								<i-lucide-chevron-down class="h-3 w-3" />
							</template>
						</Button>
					</Dropdown>
				</div>
				<div
					v-if="schedule.override !== 'None'"
					class="mt-3 flex items-center justify-between rounded-md bg-yellow-50 px-3 py-2"
				>
					<span class="text-sm text-yellow-800">
						<template v-if="schedule.override === 'Indefinite'">
							Schedule paused indefinitely
						</template>
						<template v-else-if="schedule.override === 'Until Datetime'">
							Schedule paused until {{ formattedOverrideUntil }}
						</template>
					</span>
					<Button
						variant="ghost"
						size="sm"
						@click="cancelOverride"
						:loading="$site.setScheduleOverride.loading"
					>
						Cancel
					</Button>
				</div>
			</template>
		</div>
	</div>
</template>

<script>
import { getCachedDocumentResource, createResource, Button, Dropdown } from 'frappe-ui';
import { toast } from 'vue-sonner';
import { confirmDialog } from '../../utils/components';
import { getToastErrorMessage } from '../../utils/toast';
import dayjs from '../../utils/dayjs';

export default {
	name: 'SiteScheduleCard',
	props: ['site'],
	components: { Button, Dropdown },
	data() {
		return {
			schedule: null,
			presetsResource: createResource({
				url: 'press.api.client.get_list',
				params: {
					doctype: 'Site Schedule Preset',
					fields: ['preset_name'],
					limit: 50,
				},
				auto: true,
			}),
		};
	},
	mounted() {
		this.loadSchedule();
	},
	methods: {
		async loadSchedule() {
			const result = await this.$site.getSchedule.submit();
			this.schedule = result;
		},
		showSetScheduleDialog(currentPreset = null) {
			const presets = (this.presetsResource.data || []).map(p => p.preset_name);
			confirmDialog({
				title: currentPreset ? 'Change Schedule Preset' : 'Set Instance Schedule',
				fields: [
					{
						label: 'Preset',
						fieldname: 'preset',
						fieldtype: 'Select',
						options: presets.join('\n'),
						default: currentPreset || presets[0] || '',
					},
				],
				onSuccess: ({ values }) => {
					toast.promise(
						this.$site.setSchedule.submit({ preset: values.preset }),
						{
							loading: 'Saving schedule...',
							success: () => {
								this.loadSchedule();
								return 'Schedule saved';
							},
							error: e => getToastErrorMessage(e),
						}
					);
				},
			});
		},
		toggleEnabled() {
			if (this.schedule?.enabled) {
				toast.promise(
					this.$site.disableSchedule.submit(),
					{
						loading: 'Disabling schedule...',
						success: () => {
							this.loadSchedule();
							return 'Schedule disabled';
						},
						error: e => getToastErrorMessage(e),
					}
				);
			} else {
				toast.promise(
					this.$site.setSchedule.submit({ preset: this.schedule.preset }),
					{
						loading: 'Enabling schedule...',
						success: () => {
							this.loadSchedule();
							return 'Schedule enabled';
						},
						error: e => getToastErrorMessage(e),
					}
				);
			}
		},
		showKeepRunningUntilDialog() {
			confirmDialog({
				title: 'Keep Running Until',
				fields: [
					{
						label: 'Keep running until',
						fieldname: 'override_until',
						fieldtype: 'Datetime',
					},
				],
				onSuccess: ({ values }) => {
					if (!values.override_until) return;
					toast.promise(
						this.$site.setScheduleOverride.submit({
							override_type: 'Until Datetime',
							override_until: values.override_until,
						}),
						{
							loading: 'Setting override...',
							success: () => {
								this.loadSchedule();
								return 'Override set';
							},
							error: e => getToastErrorMessage(e),
						}
					);
				},
			});
		},
		setIndefiniteOverride() {
			toast.promise(
				this.$site.setScheduleOverride.submit({ override_type: 'Indefinite' }),
				{
					loading: 'Pausing schedule...',
					success: () => {
						this.loadSchedule();
						return 'Schedule paused';
					},
					error: e => getToastErrorMessage(e),
				}
			);
		},
		cancelOverride() {
			toast.promise(
				this.$site.setScheduleOverride.submit({ override_type: 'None' }),
				{
					loading: 'Resuming schedule...',
					success: () => {
						this.loadSchedule();
						return 'Schedule resumed';
					},
					error: e => getToastErrorMessage(e),
				}
			);
		},
	},
	computed: {
		$site() {
			return getCachedDocumentResource('Site', this.site);
		},
		presetSummary() {
			const p = this.schedule?.preset_doc;
			if (!p) return '';
			const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
			const dayLabels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
			const activeDays = days
				.map((d, i) => (p[d] ? dayLabels[i] : null))
				.filter(Boolean);

			const dayStr = activeDays.join(', ');
			if (p.all_day) return `${dayStr} · All day`;

			const fmt = t => {
				if (!t) return '';
				const [h, m] = String(t).split(':');
				const hour = parseInt(h);
				const suffix = hour >= 12 ? 'pm' : 'am';
				const displayHour = hour % 12 || 12;
				return `${displayHour}:${m}${suffix}`;
			};
			return `${dayStr} · ${fmt(p.start_time)} – ${fmt(p.stop_time)}`;
		},
		formattedOverrideUntil() {
			if (!this.schedule?.override_until) return '';
			return dayjs(this.schedule.override_until).format('MMM D, h:mma');
		},
		overrideOptions() {
			return [
				{
					label: 'Keep running until…',
					onClick: () => this.showKeepRunningUntilDialog(),
				},
				{
					label: 'Run until I turn it back on',
					onClick: () => this.setIndefiniteOverride(),
				},
			];
		},
		menuOptions() {
			return [
				{
					label: 'Change Preset',
					onClick: () => this.showSetScheduleDialog(this.schedule?.preset),
				},
				{
					label: 'Disable Schedule',
					condition: () => this.schedule?.enabled,
					onClick: () => this.toggleEnabled(),
				},
			].filter(o => (o.condition ? o.condition() : true));
		},
	},
};
</script>
