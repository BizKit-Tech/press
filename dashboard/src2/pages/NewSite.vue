<template>
	<div class="sticky top-0 z-10 shrink-0">
		<Header>
			<FBreadcrumbs :items="breadcrumbs" />
		</Header>
	</div>

	<!-- Dialog -->
	<Dialog 
		v-model="showModal" 
		@close="closeModal"
		:options="{ title: 'Site Creation Started' }"
		:disableOutsideClickToClose="true"
	>
		<template #body-content>
			<p>The setup process has started and may take a few minutes. You'll be notified once the servers are ready and the site configuration is underway.</p>
		</template>
		<template #actions>
			<Button @click="closeModal">Close and Reload</Button>
		</template>
	</Dialog>

	<div
		v-if="!$team.doc?.is_desk_user && !$session.hasSiteCreationAccess"
		class="mx-auto mt-60 w-fit rounded border border-dashed px-12 py-8 text-center text-gray-600"
	>
		<i-lucide-alert-triangle class="mx-auto mb-4 h-6 w-6 text-red-600" />
		<ErrorMessage message="You aren't permitted to create new sites" />
	</div>

	<div v-else class="mx-auto max-w-2xl px-5">
		<div v-if="$resources.options.loading" class="py-4 text-base text-gray-600">
			Loading...
		</div>
		<div v-if="$route.name === 'NewBenchSite' && !bench">
			<div class="py-4 text-base text-gray-600">Something went wrong</div>
		</div>
		<div v-else-if="options" class="space-y-12 pb-[50vh] pt-12">
			<AlertBanner
				v-if="backup"
				class="mb-4"
				type="info"
				:title="`Creating site from <strong>${backup_site}</strong> backup created on <strong>${backup_date}</strong>`"
			/>
			<NewSiteAppSelector
				:availableApps="selectedVersionAppOptions"
				:siteOnPublicBench="!bench"
				v-model="apps"
			/>
			<div v-if="showLocalisationSelector" class="space-y-4">
				<div class="flex space-x-2">
					<FormControl
						label="Install Local Compliance App?"
						v-model="showLocalisationOption"
						type="checkbox"
					/>
					<Tooltip
						text="A local compliance app allows creating transactions as per statutory compliance. They're maintained by community partners."
					>
						<i-lucide-info class="h-4 w-4 text-gray-500" />
					</Tooltip>
				</div>
				<FormControl
					class="w-1/2"
					variant="outline"
					:class="{ 'pointer-events-none opacity-50': !showLocalisationOption }"
					label="Select Country"
					v-model="selectedLocalisationCountry"
					type="autocomplete"
					:options="localisationAppCountries"
				/>
			</div>
			<div v-if="!bench">
				<div class="flex items-center justify-between">
					<h2 class="text-base font-medium leading-6 text-gray-900">
						Select Frappe Framework Version
					</h2>
				</div>
				<div class="mt-2">
					<div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
						<component
							v-for="v in availableVersions"
							:key="v.name"
							:is="v.disabled ? 'Tooltip' : 'div'"
							:text="
								v.disabled && versionAppsMap[v.name]
									? `This version is not available for the ${$format.plural(
											versionAppsMap[v.name].length,
											'app',
											'apps'
									  )} ${$format.commaAnd(versionAppsMap[v.name])}`
									: ''
							"
						>
							<button
								:class="[
									version === v.name
										? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
										: 'bg-white text-gray-900  hover:bg-gray-50',
									v.disabled && 'opacity-50 hover:cursor-default',
									'flex w-full cursor-pointer items-center justify-between rounded border border-gray-400 p-3 text-sm focus:outline-none'
								]"
								@click="
									() => {
										if (v.disabled) return;
										version = v.name;
									}
								"
							>
								<span class="font-medium">{{ v.name }} </span>
								<div
									v-if="v.status === 'Develop'"
									class="flex items-center gap-2"
								>
									<Tooltip
										text="This version is under development and may have bugs. Do not use for production sites."
									>
										<i-lucide-info class="h-4 w-4 text-gray-500" />
									</Tooltip>
									<span class="ml-1 text-gray-600">
										{{ v.status }}
									</span>
								</div>
							</button>
						</component>
					</div>
				</div>
			</div>
			<div>
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Select Product
				</h2>
				<div class="grid grid-cols-2 gap-3">
					<button
						@click="product = 'ERP'"
						:class="[
							product === 'ERP'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">ERP</span>
						</div>
					</button>
					<button
						@click="product = 'HRIS'"
						:class="[
							product === 'HRIS'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">HRIS</span>
						</div>
					</button>
					<button
						@click="product = 'ERP and HRIS'"
						:class="[
							product === 'ERP and HRIS'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">ERP and HRIS</span>
						</div>
					</button>
				</div>
			</div>
			<div>
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Select Environment
				</h2>
				<div class="grid grid-cols-2 gap-3">
					<button
						@click="environment = 'Development'"
						:class="[
							environment === 'Development'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">Development</span>
						</div>
					</button>
					<button
						@click="environment = 'Production'"
						:class="[
							environment === 'Production'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">Production</span>
						</div>
					</button>
					<button
						@click="environment = 'Demo'"
						:class="[
							environment === 'Demo'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">Demo</span>
						</div>
					</button>
				</div>
			</div>
			<div v-if="environment">
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Select Tenancy
				</h2>
				<div class="grid grid-cols-2 gap-3">
					<button
						@click="tenancy = 'Dedicated'"
						:disabled="environment === 'Demo'"
						:class="[
							tenancy === 'Dedicated'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900',
							environment === 'Demo' && 'opacity-50 cursor-not-allowed'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">Dedicated</span>
						</div>
					</button>
					<button
						@click="tenancy = 'Shared'"
						:disabled="environment !== 'Demo'"
						:class="[
							tenancy === 'Shared'
								? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
								: 'bg-white text-gray-900 hover:bg-gray-50',
							'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
						]"
					>
						<div class="flex w-full items-center justify-between">
							<span class="text-sm font-medium">Shared</span>
						</div>
					</button>
				</div>
				<div class="mt-1">
					<div v-if="tenancy === 'Dedicated'" class="text-base text-gray-600">
						No other client shares the same server.
					</div>
					<div v-else class="text-base text-gray-600">
						Multiple clients may share the same server.
					</div>
				</div>
			</div>
			<div
				class="flex flex-col"
				v-if="tenancy === 'Dedicated'"
			>
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Select Project
				</h2>
				<div class="mt-2 w-full space-y-2">
					<div class="grid grid-cols-2 gap-3">
						<button
							@click="cluster = 'New Client'"
							:class="[
								cluster === 'New Client'
									? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
									: 'bg-white text-gray-900 hover:bg-gray-50',
								'flex w-full items-center rounded border p-3 text-left text-base text-gray-900',
								environment === 'Demo' && 'opacity-50 cursor-not-allowed'
							]"
						>
							<div class="flex w-full items-center justify-between">
								<span class="text-sm font-medium">New Client</span>
							</div>
						</button>
						<button
							v-for="c in selectedVersion.group.clusters"
							:key="c.name"
							@click="cluster = c.name"
							:disabled="c.name === 'Default'"
							:class="[
								cluster === c.name
									? 'border-gray-900 ring-1 ring-gray-900 hover:bg-gray-100'
									: 'bg-white text-gray-900  hover:bg-gray-50',
								'flex w-full items-center rounded border p-3 text-left text-base text-gray-900'
							]"
						>
							<div class="flex w-full items-center justify-between">
								<div class="flex w-full items-center space-x-2">
									<span class="text-sm font-medium">
										{{ c.title }}
									</span>
								</div>
								<Badge v-if="c.beta" :label="c.beta ? 'Beta' : ''" />
							</div>
						</button>
					</div>
				</div>
			</div>
			<div v-if="cluster === 'New Client'">
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Enter Project Name
				</h2>
				<div class="mt-2 items-center">
					<div class="col-span-2 flex w-full">
						<TextInput
							class="flex-1 rounded"
							placeholder="BizKit"
							v-model="projectName"
						/>
					</div>
				</div>
				<div class="mt-1">
					<div
						v-if="$resources.clusterExists.loading"
						class="text-base text-gray-600"
					>
						Checking...
					</div>
					<template
						v-else-if="
							!$resources.clusterExists.error &&
							$resources.clusterExists.data != null
						"
					>
						<div
							v-if="$resources.clusterExists.data"
							class="text-sm text-green-600"
						>
							{{ projectName }} is available.
						</div>
						<div v-else class="text-sm text-red-600">
							{{ projectName }} already exists. Please choose another name or select an existing project.
						</div>
					</template>
					<ErrorMessage :message="$resources.clusterExists.error" />
				</div>
			</div>
			<div v-if="cluster || tenancy === 'Shared'">
				<div class="flex items-center justify-between">
					<h2 class="text-base font-medium leading-6 text-gray-900">
						Select Plan
					</h2>
					<div>
						<Button link="https://frappecloud.com/pricing" variant="ghost">
							<template #prefix>
								<i-lucide-help-circle class="h-4 w-4 text-gray-700" />
							</template>
							Help
						</Button>
					</div>
				</div>
				<div class="mt-2">
					<SitePlansCards
						v-model="plan"
						:isPrivateBenchSite="!!bench"
						:isDedicatedServerSite="selectedVersion.group.is_dedicated_server"
						:selectedCluster="cluster"
						:selectedApps="apps"
						:selectedVersion="version"
						:hideRestrictedPlans="selectedLocalisationCountry"
						:selectedEnvironment="environment"
					/>
				</div>
				<div class="mt-4 text-xs text-gray-700">
					<div
						class="flex items-center rounded bg-gray-50 p-2 text-p-base font-medium text-gray-800"
					>
						<i-lucide-badge-check class="h-4 w-8 text-gray-600" />
						<span class="ml-4">
							<strong>Support</strong> covers only issues of Frappe apps and not
							functional queries. You can raise a support ticket for Frappe
							Cloud issues for all plans.
						</span>
					</div>
				</div>
			</div>
			<div v-if="false">
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Enter Subdomain
				</h2>
				<div class="mt-2 items-center">
					<div class="col-span-2 flex w-full">
						<TextInput
							class="flex-1 rounded-r-none"
							placeholder="Subdomain"
							v-model="subdomain"
						/>
						<div class="flex items-center rounded-r bg-gray-100 px-4 text-base">
							.{{ options.domain }}
						</div>
					</div>
				</div>
				<div class="mt-1">
					<div
						v-if="$resources.subdomainExists.loading"
						class="text-base text-gray-600"
					>
						Checking...
					</div>
					<template
						v-else-if="
							!$resources.subdomainExists.error &&
							$resources.subdomainExists.data != null
						"
					>
						<div
							v-if="$resources.subdomainExists.data"
							class="text-sm text-green-600"
						>
							{{ subdomain }}.{{ options.domain }} is available
						</div>
						<div v-else class="text-sm text-red-600">
							{{ subdomain }}.{{ options.domain }} is not available
						</div>
					</template>
					<ErrorMessage :message="$resources.subdomainExists.error" />
				</div>
			</div>
			<div v-if="plan && cluster">
				<h2 class="text-base font-medium leading-6 text-gray-900">
					Enter Full Company Name
				</h2>
				<div class="mt-2 items-center">
					<div class="col-span-2 flex w-full">
						<TextInput
							class="flex-1 rounded-r-none"
							placeholder="BizKit Technologies Inc."
							v-model="companyName"
						/>
						<TextInput
							class="flex items-center rounded-r bg-gray-200 text-base"
							placeholder="BTI"
							v-model="companyNameAbbr"
						/>
					</div>
				</div>
			</div>
			<Summary
				v-if="cluster && plan && companyName"
				:options="siteSummaryOptions"
			/>
			<div v-if="selectedVersion && cluster && plan && companyName">
				<Button
					class="w-full"
					variant="solid"
					@click="$resources.newSite.submit()"
					:loading="$resources.newSite.loading"
					:loadingText="'Creating site... This may take a while...'"
					:disabled="hasErrors"
				>
					Create site
				</Button>
			</div>
		</div>
	</div>
</template>
<script>
import {
	Autocomplete,
	ErrorMessage,
	FeatherIcon,
	FormControl,
	TextInput,
	Tooltip,
	debounce,
	Breadcrumbs,
	getCachedDocumentResource,
	Dialog
} from 'frappe-ui';
import SitePlansCards from '../components/SitePlansCards.vue';
import { validateSubdomain } from '../utils/site';
import Header from '../components/Header.vue';
import router from '../router';
import { plans } from '../data/plans';
import NewSiteAppSelector from '../components/site/NewSiteAppSelector.vue';
import Summary from '../components/Summary.vue';
import { DashboardError } from '../utils/error';
import { getCountry } from '../utils/country';
import AlertBanner from '../components/AlertBanner.vue';

export default {
	name: 'NewSite',
	props: ['bench', 'backup'],
	components: {
		FBreadcrumbs: Breadcrumbs,
		NewSiteAppSelector,
		SitePlansCards,
		Autocomplete,
		ErrorMessage,
		FormControl,
		FeatherIcon,
		TextInput,
		Tooltip,
		Summary,
		Header,
		AlertBanner
	},
	mounted() {
		this.initializeComponent();
	},
	unmounted() {
		if (window.posthog?.__loaded && window.posthog.sessionRecordingStarted()) {
			window.posthog.stopSessionRecording();
		}
	},
	data() {
		return {
			bench: null,
			version: null,
			subdomain: '',
			cluster: null,
			plan: null,
			apps: [],
			appPlans: {},
			selectedApp: null,
			closestCluster: null,
			selectedLocalisationCountry: null,
			showLocalisationOption: false,
			showAppPlanSelectorDialog: false,
			shareDetailsConsent: false,
			agreedToRegionConsent: false,
			product: null,
			environment: null,
			tenancy: null,
			projectName: '',
			companyName: '',
			companyNameAbbr: '',
			showModal: false,
			backup: this.backup,
		};
	},
	watch: {
		apps() {
			this.version = this.autoSelectVersion();
			this.cluster = null;
			this.agreedToRegionConsent = false;
		},
		showLocalisationOption() {
			if (this.showLocalisationOption) {
				const localisationAppCountries = this.localisationAppCountries.map(
					c => c.value
				);

				if (
					localisationAppCountries.includes(getCountry()) &&
					!this.selectedLocalisationCountry
				) {
					this.selectedLocalisationCountry = { value: getCountry() };
				}
			} else {
				this.selectedLocalisationCountry = null;
			}
		},
		async version() {
			this.cluster = null;
			this.cluster = await this.getClosestCluster();
			this.agreedToRegionConsent = false;
		},
		cluster() {
			this.plan = null;
			this.agreedToRegionConsent = false;
		},
		subdomain: {
			handler: debounce(function (value) {
				let invalidMessage = validateSubdomain(value);
				this.$resources.subdomainExists.error = invalidMessage;
				if (!invalidMessage) {
					this.$resources.subdomainExists.submit();
				}
			}, 500)
		},
		closestCluster() {
			this.cluster = this.closestCluster;
		},
		environment() {
			this.tenancy = this.getDefaultTenancy(this.environment);
		},
		projectName: {
			handler: debounce(function (value) {
				this.$resources.clusterExists.submit();
			}, 500)
		},
		companyName: {
			handler: debounce(function (value) {
				this.companyNameAbbr = value
					.split(' ')
					.map(word => word[0])
					.join('')
					.toUpperCase();
			}, 500)
		}
	},
	resources: {
		options() {
			return {
				url: 'press.api.site.options_for_new',
				makeParams() {
					return { for_bench: this.bench };
				},
				onSuccess() {
					if (this.bench && this.options.versions.length > 0) {
						this.version = this.options.versions[0].name;
					}
				},
				auto: false
			};
		},
		subdomainExists() {
			return {
				url: 'press.api.site.exists',
				makeParams() {
					return {
						domain: this.options?.domain,
						subdomain: this.subdomain
					};
				},
				validate() {
					let error = validateSubdomain(this.subdomain);
					if (error) {
						return new DashboardError(error);
					}
				},
				transform(data) {
					return !Boolean(data);
				}
			};
		},
		clusterExists() {
			return {
				url: 'press.api.site.cluster_exists',
				makeParams() {
					return {
						cluster: this.projectName
					};
				},
				validate() {
					if (!this.projectName) {
						this.$resources.clusterExists.error = 'Please enter a project name';
						return false;
					}
					const projectNameRegex = /^[a-zA-Z0-9-]+$/;
					if (!projectNameRegex.test(this.projectName)) {
						this.$resources.clusterExists.error = 'Project name contains invalid characters. Use letters, numbers, and hyphens';
						return false;
					}
					if (this.projectName.length < 5 || this.projectName.length > 32) {
						this.$resources.clusterExists.error = 'Project name must be between 5 and 32 characters';
						return false;
					}
					this.$resources.clusterExists.error = null;
					return true;
				},
				transform(data) {
					return !Boolean(data);
				}
			};
		},
		newSite() {
			if (!(this.options && this.selectedVersion)) return;

			return {
				url: 'press.api.bizkit_site.new',
				makeParams() {
					return {
						args: {
							cluster: this.cluster,
							project_name: this.selectedClusterTitle,
							company_name: this.companyName,
							company_name_abbr: this.companyNameAbbr,
							environment: this.environment,
							apps: ['frappe', ...this.apps.map(app => app.app)],
							product: this.product,
							tenancy: this.tenancy,
							site_plan: this.plan.name,
							backup: this.backup,
						}
					};
				},
				onSuccess() {
					this.showModal = true;
				}
			};
		},
		getDefaultBench() {
			return {
				url: 'press.api.site.get_default_bench',
				onSuccess(data) {
					this.bench = data;
				}
			};
		},
		getBackupDetails() {
			if (!this.backup) return;

			return {
				url: 'press.api.site.get_backup_details',
				makeParams() {
					return { backup: this.backup };
				},
				onSuccess(data) {
					this.backup_site = data.site;
					this.backup_date = data.creation;
				},
				auto: true
			};
		}
	},
	computed: {
		hasErrors() {
            return (
                this.$resources.clusterExists.error ||
                this.$resources.subdomainExists.error ||
                !this.selectedVersion ||
                !this.cluster ||
                !this.plan ||
                !this.companyName
            );
        },
		options() {
			return this.$resources.options.data;
		},
		selectedVersion() {
			return this.options?.versions.find(v => v.name === this.version);
		},
		availableVersions() {
			if (!this.apps.length || this.bench)
				return this.options.versions.sort((a, b) =>
					b.name.localeCompare(a.name)
				);

			let commonVersions = this.apps.reduce((acc, app) => {
				if (!acc) return app.sources.map(s => s.version);
				return acc.filter(v => app.sources.map(s => s.version).includes(v));
			}, null);

			if (this.selectedLocalisationCountry) {
				// temporary override since we don't have localisation app ready for v14
				// TODO: remove this when localisation app is ready for v14
				commonVersions = ['Version 15'];
				this.version = 'Version 15';
			}

			return this.options.versions.map(v => ({
				...v,
				disabled: !commonVersions.includes(v.name)
			}));
		},
		selectedClusterTitle() {
			if (this.cluster === 'New Client') return this.projectName;
			return this.selectedVersion?.group?.clusters?.find(
				c => c.name === this.cluster
			)?.title;
		},
		selectedVersionApps() {
			let apps = [];

			if (!this.bench)
				apps = this.options.app_source_details.sort((a, b) =>
					a.total_installs !== b.total_installs
						? b.total_installs - a.total_installs
						: a.app.localeCompare(b.app)
				);
			else if (!this.selectedVersion?.group?.bench_app_sources) apps = [];
			else
				apps = this.selectedVersion.group.bench_app_sources.map(app_source => {
					let app_source_details = this.options.app_source_details[app_source];

					let marketplace_details = app_source_details
						? this.options.marketplace_details[app_source_details.app]
						: {};

					return {
						app_title: app_source,
						...app_source_details,
						...marketplace_details
					};
				});

			// sorted by total installs and then by name
			return apps.sort((a, b) => {
				if (a.total_installs > b.total_installs) {
					return -1;
				} else if (a.total_installs < b.total_installs) {
					return 1;
				} else {
					return a.app_title.localeCompare(b.app_title);
				}
			});
		},
		selectedVersionAppOptions() {
			return this.selectedVersionApps.filter(
				app => !this.localisationAppNames.includes(app.app)
			);
		},
		showLocalisationSelector() {
			if (
				!this.selectedVersionApps ||
				!this.localisationAppNames.length ||
				!this.apps.length
			)
				return false;

			const appsThatNeedLocalisation = this.selectedVersionApps.filter(
				app => app.localisation_apps.length
			);

			if (
				appsThatNeedLocalisation.some(app =>
					this.apps.map(a => a.app).includes(app.app)
				)
			)
				return true;

			return false;
		},
		localisationAppNames() {
			if (!this.selectedVersionApps) return [];
			const localisationAppDetails = this.selectedVersionApps.flatMap(
				app => app.localisation_apps
			);

			return localisationAppDetails
				.map(app => app?.marketplace_app)
				.filter(Boolean);
		},
		localisationAppCountries() {
			if (!this.selectedVersionApps) return [];
			const localisationAppDetails = this.selectedVersionApps.flatMap(
				app => app.localisation_apps
			);
			return localisationAppDetails.map(app => ({
				label: app?.country,
				value: app?.country
			}));
		},
		selectedPlan() {
			if (!plans?.data) return;
			return plans.data.find(p => p.name === this.plan.name);
		},
		versionAppsMap() {
			const versions = this.availableVersions.map(v => v.name);
			let problemAppVersions = {};
			if (!this.bench)
				for (let app of this.apps) {
					const appVersions = app.sources.map(s => s.version);
					const problemVersions = versions.filter(
						version => !appVersions.includes(version)
					);
					for (let version of problemVersions) {
						if (!problemAppVersions[version]) {
							problemAppVersions[version] = [];
						}
						problemAppVersions[version].push(app.app_title);
					}
				}
			return problemAppVersions;
		},
		breadcrumbs() {
			if (this.bench) {
				let group = getCachedDocumentResource('Release Group', this.bench);
				return [
					{ label: 'Bench Groups', route: '/groups' },
					{
						label: group ? group.doc.title : this.bench,
						route: {
							name: 'Release Group Detail',
							params: { name: this.bench }
						}
					},
					{
						label: 'New Site',
						route: {
							name: 'Release Group New Site',
							params: { bench: this.bench }
						}
					}
				];
			}
			return [
				{ label: 'Sites', route: '/sites' },
				{ label: 'New Site', route: '/sites/new' }
			];
		},
		_totalPerMonth() {
			let total =
				this.$team.doc.currency == 'PHP'
					? this.selectedPlan.price_inr
					: this.selectedPlan.price_usd;

			for (let app of this.apps.filter(app => app.plan)) {
				total +=
					this.$team.doc.currency == 'PHP'
						? app.plan.price_inr
						: app.plan.price_usd;
			}

			return total;
		},
		totalPerMonth() {
			return this.$format.userCurrency(this._totalPerMonth);
		},
		totalPerDay() {
			return this.$format.userCurrency(
				this.$format.pricePerDay(this._totalPerMonth)
			);
		},
		siteSummaryOptions() {
			let appPlans = [];
			for (let app of this.apps) {
				appPlans.push(
					`${this.selectedVersionApps.find(a => a.app === app.app).app_title} ${
						app.plan?.price_inr
							? `- <span class="text-gray-600">${this.$format.userCurrency(
									this.$team.doc.currency == 'PHP'
										? app.plan.price_inr
										: app.plan.price_usd
							  )} per month</span>`
							: ''
					}`
				);
			}

			return [
				{
					label: 'Frappe Framework Version',
					value: this.selectedVersion?.name
				},
				{
					label: 'Product',
					value: this.product
				},
				{
					label: 'Environment',
					value: this.environment
				},
				{
					label: 'Project Name',
					value: this.selectedClusterTitle
				},
				{
					label: 'Full Company Name',
					value: this.companyName
				},
				{
					label: 'Company Name Abbreviation',
					value: this.companyNameAbbr
				},
				{
					label: 'Site Plan',
					value: `${this.$format.userCurrency(
						this.$team.doc.currency == 'PHP'
							? this.selectedPlan.price_inr
							: this.selectedPlan.price_usd
					)} per month`
				},
				{
					label: 'Apps',
					value: this.apps.length ? appPlans.join('<br>') : 'No apps selected'
				},
				{
					label: 'Total',
					value: `${this.totalPerMonth} per month <div class="text-gray-600">${this.totalPerDay} per day</div>`,
					condition: () => this._totalPerMonth
				}
			];
		}
	},
	methods: {
		async initializeComponent() {
			if (!this.$team.doc.onboarding.site_created && window.posthog?.__loaded) {
				window.posthog.identify(this.$team.doc.user, {
					app: 'frappe_cloud',
					action: 'first_new_site_creation'
				});
				if (!window.posthog.sessionRecordingStarted()) {
					window.posthog.startSessionRecording();
				}
			}

			if (!this.bench) {
				await this.$resources.getDefaultBench.submit();
			}

			this.$resources.options.submit();
		},
		async getClosestCluster() {
			if (this.closestCluster) return this.closestCluster;
			let proxyServers = this.selectedVersion?.group?.clusters
				.flatMap(c => c.proxy_server || [])
				.map(server => server.name);

			if (proxyServers.length > 0) {
				this.findingClosestServer = true;
				let promises = proxyServers.map(server => this.getPingTime(server));
				let results = await Promise.allSettled(promises);
				let fastestServer = results.reduce((a, b) =>
					a.value.pingTime < b.value.pingTime ? a : b
				);
				let closestServer = fastestServer.value.server;
				let closestCluster = this.selectedVersion?.group?.clusters.find(
					c => c.proxy_server?.name === closestServer
				);
				if (!this.closestCluster) {
					this.closestCluster = closestCluster.name;
				}
				this.findingClosestServer = false;
			} else if (proxyServers.length === 1) {
				this.closestCluster = this.selectedVersion?.group?.clusters[0].name;
			}
			return this.closestCluster;
		},
		async getPingTime(server) {
			let pingTime = 999999;
			try {
				let t1 = new Date().getTime();
				let r = await fetch(`https://${server}`);
				let t2 = new Date().getTime();
				pingTime = t2 - t1;
			} catch (error) {
				console.warn(error);
			}
			return { server, pingTime };
		},
		autoSelectVersion() {
			if (!this.availableVersions) return null;

			return this.availableVersions
				.sort((a, b) => b.name.localeCompare(a.name))
				.find(v => !v.disabled)?.name;
		},
		getDefaultTenancy(environment) {
			if (environment === 'Demo') {
				return 'Shared';
			} else {
				return 'Dedicated';
			}
		},
		closeModal() {
			this.showModal = false;
			router.push({ name: 'Site List' });
		},
	}
};
</script>
<style scoped>
.checkbox:deep(label) {
	color: theme('colors.gray.700') !important;
	line-height: 1.5;
}
</style>
