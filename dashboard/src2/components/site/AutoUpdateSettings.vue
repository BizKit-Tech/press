<template>
	<div>
		<div class="flex p-5 gap-7.5">
			<Switch
				class="mr-8"
				label="Enable Automatic Updates"
				description="If unchecked, this site will not receive automatic updates which include new features and bug fixes."
				v-model="enableUpdates"
				@click="isDirty = true"
			/>
			<FormControl
				v-if="enableUpdates"
				label="Update Trigger Frequency"
				type="select"
				v-model="updateFrequency"
				:disabled="!enableUpdates"
				:options="[
					'Daily',
					'Weekly',
					'Every 2 Weeks'
				]"
				@change="isDirty = true"
			/>
			<FormControl
				v-if="enableUpdates && updateFrequency === 'Every 2 Weeks'"
				label="Update Start Date"
				type="date"
				v-model="updateStartDate"
				:disabled="!enableUpdates"
				@change="isDirty = true"
			/>
			<FormControl
				v-if="enableUpdates && updateFrequency !== 'Daily'"
				label="Update Trigger Day"
				type="select"
				v-model="updateDay"
				:disabled="!enableUpdates"
				:options="[
					'Monday',
					'Tuesday',
					'Wednesday',
					'Thursday'
				]"
				@change="isDirty = true"
			/>
			<FormControl
				v-if="enableUpdates"
				label="Update Trigger Time"
				type="time"
				v-model="updateTriggerTime"
				:disabled="!enableUpdates"
				@change="isDirty = true"
			/>
			<Button
				size="sm"
				class="my-5"
				variant="solid"
				:label="isDirty ? 'Save' : 'Saved'"
				@click="siteResource.setValue.submit(
					{ 
						skip_auto_updates: !enableUpdates,
						update_trigger_frequency: updateFrequency,
						update_on_weekday: updateDay,
						update_trigger_time: updateTriggerTime
					},
					{
						onSuccess() {
							toast.success('Auto Update settings updated successfully.');
							isDirty = false;
						},
						onError() {
							toast.error('Failed to update Auto Update settings.');
							setTimeout(() => window.location.reload(), 1000);
						},
					},
				)"
				:loading="siteResource.setValue.loading"
				loadingText="Saving"
				:disabled="!isDirty"
			/>
		</div>
		<ObjectList class="pl-5" :options="logsOptions" />
	</div>
</template>

<script setup>

import { 
	createResource,
	createDocumentResource,
} from 'frappe-ui';
import { toast } from 'vue-sonner';
import { computed, ref, toRefs } from 'vue';
import { confirmDialog, icon } from '../../utils/components';
import { duration } from '../../utils/format';
import ObjectList from '../ObjectList.vue';
import router from '../../router';

const props = defineProps({
	site: {
		type: String,
		required: true
	}
});

const isDirty = ref(false);

const siteResource = createDocumentResource({
	doctype: 'Site',
	name: props.site,
	auto: true,
});

const siteValues = computed(() => {
	if (!siteResource.doc) return {};
	return {
		enableUpdates: !siteResource.doc.skip_auto_updates,
		updateFrequency: siteResource.doc.update_trigger_frequency,
		updateDay: siteResource.doc.update_on_weekday,
		updateTriggerTime: siteResource.doc.update_trigger_time
	};
});

const enableUpdates = ref(siteValues.value?.enableUpdates);
const updateFrequency = ref(siteValues.value?.updateFrequency);
const updateStartDate = ref(null);
const updateDay = ref(siteValues.value?.updateDay);
const updateTriggerTime = ref(siteValues.value?.updateTriggerTime);

const logsResource = createResource({
	url: 'press.api.client.get_list',
	params: {
		doctype: 'Agent Job',
		filters: {
			site: props.site,
			job_type: 'Update Site'
		},
		order_by: 'creation desc',
		fields: ['name', 'end', 'job_id', 'job_type', 'status', 'duration', 'owner', 'creation'],
	},
	initialData: [],
	auto: true
});

const logsOptions = computed(() => ({
	data: () => logsResource.data,
	columns: [
		{
			label: 'Job Type',
			fieldname: 'job_type',
			class: 'font-medium'
		},
		{
			label: 'Status',
			fieldname: 'status',
			type: 'Badge',
			width: 0.5
		},
		{
			label: 'Duration',
			fieldname: 'duration',
			width: 0.35,
			format(value, row) {
				if (!row.end) return;
				return duration(value);
			}
		},
		{
			label: 'Created By',
			fieldname: 'owner'
		},
		{
			label: '',
			fieldname: 'creation',
			type: 'Timestamp',
			width: 0.5,
			align: 'right'
		}
	],
	primaryAction({ listResource }) {
		return {
			label: 'Get Updates',
			slots: {
				prefix: icon('arrow-up-circle')
			},
			onClick() {
				confirmDialog({
					title: 'Get Updates',
					message:
						'Are you sure you want to update the site? This will apply the latest changes and may take some time.',
					onSuccess({ hide }) {
						toast.promise(
							siteResource.updateSite.submit(),
							{
								loading: 'Scheduling site update...',
								success: () => {
									hide();
									return 'Site update scheduled successfully.';
								},
								error: e => getToastErrorMessage(e)
							}
						);
					}
				});
			}
		};
	},
	secondaryAction() {
		return {
			label: 'Refresh',
			icon: 'refresh-ccw',
			onClick: () => logsResource.reload()
		};
	},
	rowActions({ row, listResource: configs, documentResource: site }) {
		return [
			{
				label: 'View Log',
				onClick() {
					router.push({
						name: 'Site Job',
						params: {
							name: props.site,
							id: row.name
						}
					});
				}
			}
		];
	}
}));

</script>