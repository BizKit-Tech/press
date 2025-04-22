<template>
	<Dialog
		:options="{ title: 'New Config Import' }"
		v-model="showDialog"
	>
		<template v-slot:body-content>
			<div class="space-y-4">
				<FormControl
					type="select"
					label="Configuration Type"
					:options="[
						'Roles and Permissions',
						'Field Properties',
						'Accounts Settings',
						'Buying Settings',
						'Selling Settings',
						'Stock Settings',
						'System Settings'
					]"
					v-model="configType"
				/>
				<FormControl
					type="select"
					label="Sheet Type"
					:options="[
						'Google Sheets',
						'Excel'
					]"
					v-model="sheetType"
				/>
				<FormControl
					v-if="sheetType === 'Google Sheets'"
					type="text"
					label="Google Sheet URL"
					v-model="googleSheetURL"
					placeholder="https://docs.google.com/spreadsheets/"
					autocomplete="off"
				/>
				<Button
					v-if="sheetType === 'Google Sheets'"
					@click="$resources.testGoogleSheetAccess.submit()"
					:loading="$resources.testGoogleSheetAccess.loading"
					:loadingText="'Testing...'"
					variant="subtle"
					class="w-full font-medium"
					type="button"
				>
					Test Access
				</Button>
				<p
					v-if="googleSheetStatusMessage"
					class="text-xs text-gray-600"
					:class="{
						'text-green-600': googleSheetStatus === 'Accessible',
						'text-red-600': googleSheetStatus === 'Inaccessible'
					}"
				>
					{{ googleSheetStatusMessage }}
				</p>
				<FormControl
					v-if="sheetType === 'Excel'"
					type="file"
					label="Excel File"
					v-model="excelFile"
					:accept="['.xlsx', '.xls']"
					autocomplete="off"
				/>
			</div>
		</template>
		<template #actions>
			<Button
				class="mt-2 w-full"
				variant="solid"
				:loading="$resources.newConfig.loading"
				:loadingText="'Importing...'"
				@click="$resources.newConfig.submit()"
				:disabled="!configType || !sheetType || (sheetType === 'Google Sheets' && !googleSheetURL && googleSheetStatus !== 'Accessible') || (sheetType === 'Excel' && !excelFile)"
			>
				Start Import
			</Button>
		</template>
	</Dialog>
</template>
<script>
import {
	Autocomplete,
	ErrorMessage,
	FormControl,
	getCachedDocumentResource
} from 'frappe-ui';

export default {
	name: 'NewConfigImportDialog',
	props: ['site', 'group', 'config'],
	components: {
		Autocomplete,
		FormControl,
		ErrorMessage
	},
	data() {
		return {
			docResource: null,
			showDialog: true,
			configType: null,
			sheetType: null,
			googleSheetURL: '',
			googleSheetStatus: 'Not Tested',
			googleSheetStatusMessage: null,
			excelFile: null,
		};
	},
	resources: {
		newConfig() {
			return {
				url: 'press.api.site.new_config_import',
				makeParams() {
					return {
						args: {
							site: this.site,
							configuration_type: this.configType,
							sheet_type: this.sheetType,
							google_sheet_url: this.googleSheetURL,
							google_sheet_access_status: this.googleSheetStatus,
							excel_file: this.excelFile,
						}
					};
				},
				onSuccess() {
					this.$emit('success');
					this.showDialog = false;
				},
				onError(error) {
					console.error(error);
				}
			};
		},
		testGoogleSheetAccess() {
			return {
				url: 'press.api.site.test_google_sheet_permission',
				makeParams() {
					return {
						sheet_type: this.sheetType,
						google_sheet_url: this.googleSheetURL
					};
				},
				onSuccess(result) {
					const status = result;
					this.googleSheetStatus = status;
					if (status === 'Accessible') {
						this.googleSheetStatusMessage =
							'Google Sheet is accessible';
					} else if (status === 'Inaccessible') {
						this.googleSheetStatusMessage =
							'Google Sheet is inaccessible. Please check if the URL is correct and the sheet is shared with the correct permissions.';
					} else {
						this.googleSheetStatusMessage = status;
					}

				},
				onError(error) {
					console.error(error);
					this.googleSheetStatusMessage = error.message;
				}
			};
		}
	}
};
</script>
