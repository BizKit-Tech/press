<template>
	<FrappeUIBadge :size="size" :theme="_color">
		{{ label }}
		<template #prefix>
			<slot name="prefix"></slot>
		</template>
		<template #suffix>
			<slot name="suffix"></slot>
		</template>
	</FrappeUIBadge>
</template>

<script>
import { Badge as FrappeUIBadge } from 'frappe-ui';

export default {
	name: 'Badge',
	props: ['label', 'theme', 'size'],
	components: {
		FrappeUIBadge
	},
	computed: {
		_color() {
			if (this.theme) return this.theme;
			return {
				Approved: 'green',
				Broken: 'red',
				Installing: 'orange',
				Running: 'blue',
				Pending: 'orange',
				Failure: 'red',
				Failed: 'red',
				'Update Available': 'blue',
				Enabled: 'blue',
				'Awaiting Approval': 'orange',
				'Awaiting Deploy': 'orange',
				Success: 'green',
				Completed: 'green',
				Deployed: 'green',
				Expired: 'red',
				Paid: 'green',
				Unpaid: 'orange',
				'Invoice Created': 'blue',
				Rejected: 'red',
				'In Review': 'orange',
				'Attention Required': 'red',
				Active: 'green',
				Trial: 'orange',
				Published: 'green',
				Owner: 'blue',
				Primary: 'green',
				'Latest Deployed': 'orange',
				'Not Deployed': 'orange',
				'Action Required': 'red',
				'First Deploy': 'green',
				'Will be Uninstalled': 'red'
			}[this.label];
		}
	}
};
</script>
