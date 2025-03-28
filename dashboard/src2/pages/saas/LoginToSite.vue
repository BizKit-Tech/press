<template>
	<div
		class="flex h-screen w-screen items-center justify-center"
		v-if="$resources.saasProduct.loading || $resources.siteRequest.loading"
	>
		<Spinner class="mr-2 w-4" />
		<p class="text-gray-800">Loading</p>
	</div>
	<div class="flex h-screen overflow-hidden sm:bg-gray-50" v-else>
		<div class="w-full overflow-auto">
			<SaaSLoginBox
				v-if="this.$resources?.siteRequest?.doc?.status === 'Site Created'"
				title="Logging in to site"
				:subtitle="this.$resources?.siteRequest?.doc?.site"
				:logo="saasProduct?.logo"
			>
				<div
					class="flex h-40 items-center justify-center"
					v-if="
						this.$resources?.siteRequest?.getLoginSid.loading ||
						isRedirectingToSite
					"
				>
					<Spinner class="mr-2 w-4" />
					<p class="text-base text-gray-800">Please wait for a moment</p>
				</div>
				<ErrorMessage
					v-if="!isRedirectingToSite"
					class="w-full text-center"
					:message="this.$resources?.siteRequest?.getLoginSid.error"
				/>
			</SaaSLoginBox>
			<SaaSLoginBox
				v-else-if="this.$resources?.siteRequest?.doc?.status === 'Error'"
				title="Site creation failed"
				:subtitle="this.$resources?.siteRequest?.doc?.site"
				:logo="saasProduct?.logo"
			>
				<template v-slot:default>
					<div class="flex h-40 flex-col items-center justify-center px-10">
						<Button variant="outline" @click="signupForCurrentProduct"
							>Signup for new site</Button
						>
						<p class="my-4 text-gray-600">or,</p>
						<p class="text-center text-base leading-5 text-gray-800">
							Contact at
							<a href="mailto:support@frappe.io" class="underline"
								>support@frappe.io</a
							><br />
							to resolve the issue
						</p>
					</div>
				</template>
			</SaaSLoginBox>
			<SaaSLoginBox
				v-else
				title="Building your site"
				:subtitle="this.$resources?.siteRequest?.doc?.site"
				:logo="saasProduct?.logo"
			>
				<template v-slot:default>
					<div class="flex h-40 items-center justify-center">
						<Progress
							class="px-10"
							size="lg"
							:value="progressCount"
							:label="currentBuildStep"
							:hint="true"
						/>
					</div>
				</template>
			</SaaSLoginBox>
		</div>
	</div>
</template>
<script>
import SaaSLoginBox from '../../components/auth/SaaSLoginBox.vue';
import { Progress } from 'frappe-ui';

export default {
	name: 'SaaSSignupLoginToSite',
	props: ['productId'],
	components: {
		SaaSLoginBox,
		Progress
	},
	data() {
		return {
			product_trial_request: this.$route.query.product_trial_request,
			progressCount: 0,
			isRedirectingToSite: false,
			currentBuildStep: 'Preparing for build'
		};
	},
	resources: {
		saasProduct() {
			return {
				type: 'document',
				doctype: 'Product Trial',
				name: this.productId,
				auto: true
			};
		},
		siteRequest() {
			return {
				type: 'document',
				doctype: 'Product Trial Request',
				name: this.product_trial_request,
				realtime: true,
				auto: true,
				onSuccess(doc) {
					if (
						doc.status == 'Wait for Site' ||
						doc.status == 'Completing Setup Wizard'
					) {
						this.$resources.siteRequest.getProgress.reload();
					}

					if (doc.status == 'Site Created') {
						this.loginToSite();
					}
				},
				whitelistedMethods: {
					getProgress: {
						method: 'get_progress',
						makeParams() {
							return {
								current_progress:
									this.$resources.siteRequest.getProgress.data?.progress || 0
							};
						},
						onSuccess: data => {
							this.currentBuildStep =
								data.current_step || this.currentBuildStep;
							this.progressCount += 1;
							if (data.progress == 100) {
								this.loginToSite();
							} else if (
								!(
									this.$resources.siteRequest.getProgress.error &&
									this.progressCount <= 10
								)
							) {
								this.progressCount = Math.round(data.progress * 10) / 10;
								setTimeout(() => {
									this.$resources.siteRequest.getProgress.reload();
								}, 2000);
							}
						}
					},
					getLoginSid: {
						method: 'get_login_sid',
						onSuccess(data) {
							let sid = data;
							let redirectRoute =
								this.$resources?.saasProduct?.doc?.redirect_to_after_login ??
								'/desk';
							let loginURL = `https://${this.$resources.siteRequest.doc.site}${redirectRoute}?sid=${sid}`;
							this.isRedirectingToSite = true;
							window.open(loginURL, '_self');
						}
					}
				}
			};
		}
	},
	computed: {
		saasProduct() {
			return this.$resources.saasProduct.doc;
		}
	},
	methods: {
		loginToSite() {
			this.$resources.siteRequest.getLoginSid.submit();
		},
		signupForCurrentProduct() {
			this.$router.push({
				name: 'SaaSSignupSetup',
				params: { productId: this.productId }
			});
		}
	}
};
</script>
