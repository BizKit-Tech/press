# Copyright (c) 2021, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

import contextlib
import json
import re
from collections import defaultdict
from contextlib import suppress
from functools import cached_property, wraps
from typing import Any

import dateutil.parser
import frappe
import frappe.data
import frappe.utils
import pytz
import requests
from frappe import _
from frappe.core.utils import find
from frappe.frappeclient import FrappeClient
from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import (
	add_to_date,
	cint,
	comma_and,
	cstr,
	flt,
	get_datetime,
	get_url,
	now_datetime,
	sbool,
	time_diff_in_hours,
)
from frappe.model.rename_doc import get_link_fields
from frappe.model.docstatus import DocStatus
from frappe.model.dynamic_links import get_dynamic_link_map

from press.exceptions import (
	CannotChangePlan,
	InsufficientSpaceOnServer,
	SiteAlreadyArchived,
	SiteUnderMaintenance,
	VolumeResizeLimitError,
)
from press.marketplace.doctype.marketplace_app_plan.marketplace_app_plan import (
	MarketplaceAppPlan,
)
from press.utils.webhook import create_webhook_event

try:
	from frappe.utils import convert_utc_to_user_timezone
except ImportError:
	from frappe.utils import (
		convert_utc_to_system_timezone as convert_utc_to_user_timezone,
	)

from typing import TYPE_CHECKING

from frappe.utils.password import get_decrypted_password
from frappe.utils.user import is_system_user

from press.agent import Agent, AgentRequestSkippedException
from press.api.client import dashboard_whitelist
from press.api.site import check_dns, get_updates_between_current_and_next_apps
from press.overrides import get_permission_query_conditions_for_doctype
from press.press.doctype.marketplace_app.marketplace_app import (
	get_plans_for_app,
	marketplace_app_hook,
)
from press.press.doctype.resource_tag.tag_helpers import TagHelpers
from press.press.doctype.server.server import is_dedicated_server
from press.press.doctype.site_activity.site_activity import log_site_activity
from press.press.doctype.site_analytics.site_analytics import create_site_analytics
from press.press.doctype.site_plan.site_plan import UNLIMITED_PLANS, get_plan_config
from press.press.report.mariadb_slow_queries.mariadb_slow_queries import (
	get_doctype_name,
)
from press.utils import (
	convert,
	fmt_timedelta,
	get_client_blacklisted_keys,
	get_current_team,
	guess_type,
	human_readable,
	log_error,
	unique,
)
from press.utils.dns import _change_dns_record, create_dns_record
from press.press.doctype.site.site_setup import SiteSetup
from press.press.doctype.site.backup_restore import BackupRestore

if TYPE_CHECKING:
	from datetime import datetime

	from frappe.types.DF import Table

	from press.press.doctype.bench.bench import Bench
	from press.press.doctype.bench_app.bench_app import BenchApp
	from press.press.doctype.database_server.database_server import DatabaseServer
	from press.press.doctype.deploy_candidate.deploy_candidate import DeployCandidate
	from press.press.doctype.release_group.release_group import ReleaseGroup
	from press.press.doctype.server.server import BaseServer, Server

DOCTYPE_SERVER_TYPE_MAP = {
	"Server": "Application",
	"Database Server": "Database",
	"Proxy Server": "Proxy",
}


class Site(Document, TagHelpers):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from press.press.doctype.resource_tag.resource_tag import ResourceTag
		from press.press.doctype.site_app.site_app import SiteApp
		from press.press.doctype.site_config.site_config import SiteConfig

		_keys_removed_in_last_update: DF.Data | None
		_site_usages: DF.Data | None
		account_request: DF.Link | None
		additional_system_user_created: DF.Check
		admin_password: DF.Password | None
		apps: DF.Table[SiteApp]
		archive_failed: DF.Check
		auto_update_last_triggered_on: DF.Datetime | None
		backup_time: DF.Time | None
		bench: DF.Link
		cluster: DF.Link
		company_name: DF.Data
		company_name_abbreviation: DF.Data
		config: DF.Code | None
		configuration: DF.Table[SiteConfig]
		current_cpu_usage: DF.Int
		current_database_usage: DF.Int
		current_disk_usage: DF.Int
		database_access_connection_limit: DF.Int
		database_name: DF.Data | None
		domain: DF.Link | None
		erpnext_consultant: DF.Link | None
		free: DF.Check
		group: DF.Link
		hide_config: DF.Check
		host_name: DF.Data | None
		hybrid_saas_pool: DF.Link | None
		is_erpnext_setup: DF.Check
		is_standby: DF.Check
		notify_email: DF.Data | None
		only_update_at_specified_time: DF.Check
		plan: DF.Link | None
		product: DF.Literal["ERP", "HRIS", "ERP and HRIS"]
		remote_config_file: DF.Link | None
		remote_database_file: DF.Link | None
		remote_private_file: DF.Link | None
		remote_public_file: DF.Link | None
		restored_from_backup: DF.Link | None
		saas_communication_secret: DF.Data | None
		server: DF.Link
		setup_wizard_complete: DF.Check
		setup_wizard_status_check_next_retry_on: DF.Datetime | None
		setup_wizard_status_check_retries: DF.Int
		skip_auto_updates: DF.Check
		skip_failing_patches: DF.Check
		skip_scheduled_backups: DF.Check
		staging: DF.Check
		standby_for: DF.Link | None
		standby_for_product: DF.Link | None
		status: DF.Literal["Pending", "Installing", "Updating", "Active", "Inactive", "Broken", "Archived", "Suspended"]
		status_before_update: DF.Data | None
		subdomain: DF.Data
		tags: DF.Table[ResourceTag]
		team: DF.Link
		tenancy: DF.Literal["Dedicated", "Shared"]
		timezone: DF.Data | None
		trial_end_date: DF.Date | None
		update_end_of_month: DF.Check
		update_on_day_of_month: DF.Int
		update_on_weekday: DF.Literal["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
		update_trigger_frequency: DF.Literal["Daily", "Weekly", "Monthly"]
		update_trigger_time: DF.Time | None
	# end: auto-generated types

	DOCTYPE = "Site"

	dashboard_fields = (
		"ip",
		"status",
		"group",
		"notify_email",
		"team",
		"plan",
		"setup_wizard_complete",
		"archive_failed",
		"cluster",
		"bench",
		"group",
		"database_access_connection_limit",
		"trial_end_date",
		"tags",
		"server",
		"host_name",
		"skip_auto_updates",
		"additional_system_user_created",
		"domain",
	)

	@staticmethod
	def get_list_query(query, filters=None, **list_args):
		from press.press.doctype.site_update.site_update import (
			benches_with_available_update,
		)

		Site = frappe.qb.DocType("Site")

		status = filters.get("status")
		if status == "Archived":
			sites = query.where(Site.status == status).run(as_dict=1)
		else:
			benches_with_available_update = benches_with_available_update()
			sites = query.where(Site.status != "Archived").select(Site.bench).run(as_dict=1)

			for site in sites:
				if site.bench in benches_with_available_update:
					site.status = "Update Available"

		return sites

	@staticmethod
	def on_not_found(name):
		# If name is a custom domain then redirect to the site name
		site_name = frappe.db.get_value("Site Domain", name, "site")
		if site_name:
			frappe.response.message = {
				"redirect": f"/dashboard/sites/{site_name}",
			}
		raise

	def get_doc(self, doc):
		from press.api.client import get

		group = frappe.db.get_value(
			"Release Group",
			self.group,
			["title", "public", "team", "central_bench", "version"],
			as_dict=1,
		)
		doc.group_title = group.title
		doc.version = group.version
		doc.group_team = group.team
		doc.group_public = group.public or group.central_bench
		doc.latest_frappe_version = frappe.db.get_value(
			"Frappe Version", {"status": "Stable", "public": True}, order_by="name desc"
		)
		doc.eol_versions = frappe.db.get_all(
			"Frappe Version",
			filters={"status": "End of Life"},
			fields=["name"],
			order_by="name desc",
			pluck="name",
		)
		doc.owner_email = frappe.db.get_value("Team", self.team, "user")
		doc.current_usage = self.current_usage
		doc.current_plan = get("Site Plan", self.plan) if self.plan else None
		doc.last_updated = self.last_updated
		doc.has_scheduled_updates = bool(
			frappe.db.exists("Site Update", {"site": self.name, "status": "Scheduled"})
		)
		doc.update_information = self.get_update_information()
		doc.actions = self.get_actions()
		server = frappe.get_value("Server", self.server, ["ip", "proxy_server", "team", "title"], as_dict=1)
		doc.cluster = frappe.db.get_value("Cluster", self.cluster, ["title", "image"], as_dict=1)
		doc.outbound_ip = server.ip
		doc.server_team = server.team
		doc.server_title = server.title
		doc.inbound_ip = self.inbound_ip
		doc.is_dedicated_server = is_dedicated_server(self.server)

		if broken_domain_tls_certificate := frappe.db.get_value(
			"Site Domain", {"site": self.name, "status": "Broken"}, "tls_certificate"
		):
			doc.broken_domain_error = frappe.db.get_value(
				"TLS Certificate", broken_domain_tls_certificate, "error"
			)

		return doc

	def site_action(allowed_status: list[str]):
		def outer_wrapper(func):
			@wraps(func)
			def wrapper(inst, *args, **kwargs):
				user_type = frappe.session.data.user_type or frappe.get_cached_value(
					"User", frappe.session.user, "user_type"
				)
				if user_type == "System User":
					return func(inst, *args, **kwargs)
				status = frappe.get_value(inst.doctype, inst.name, "status", for_update=True)
				if status not in allowed_status:
					frappe.throw(
						f"Site action not allowed for site with status: {frappe.bold(status)}.\nAllowed status are: {frappe.bold(comma_and(allowed_status))}."
					)
				return func(inst, *args, **kwargs)

			return wrapper

		return outer_wrapper

	def _get_site_name(self, subdomain: str):
		"""Get full site domain name given subdomain."""
		if not self.domain:
			self.domain = frappe.db.get_single_value("Press Settings", "domain")
		return f"{subdomain}.{self.domain}"

	def autoname(self):
		self.name = self._get_site_name(self.subdomain)

	def validate(self):
		if self.has_value_changed("subdomain"):
			self.validate_site_name()
		self.validate_bench()
		self.set_site_admin_password()
		self.validate_installed_apps()
		self.validate_host_name()
		self.validate_site_config()
		self.validate_auto_update_fields()
		self.validate_site_plan()

	def before_insert(self):
		if not self.bench and self.group:
			self.set_latest_bench()
		# initialize site.config based on plan
		self._update_configuration(self.get_plan_config(), save=False)
		if not self.notify_email and self.team != "Administrator":
			self.notify_email = frappe.db.get_value("Team", self.team, "notify_email")
		if not self.setup_wizard_status_check_next_retry_on:
			self.setup_wizard_status_check_next_retry_on = now_datetime()

	def validate_site_name(self):
		site_regex = r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
		if not re.match(site_regex, self.subdomain):
			frappe.throw(
				"Subdomain contains invalid characters. Use lowercase characters, numbers and hyphens"
			)
		if len(self.subdomain) > 32:
			frappe.throw("Subdomain too long. Use 32 or less characters")

		if len(self.subdomain) < 3:
			frappe.throw("Subdomain too short. Use 3 or more characters")

	def set_site_admin_password(self):
		# set site.admin_password if doesn't exist
		if not self.admin_password:
			self.admin_password = frappe.generate_hash(length=16)

	def validate_bench(self):
		if (
			self.status not in ("Broken", "Archived")
			and frappe.db.get_value("Bench", self.bench, "status", for_update=True) == "Archived"
		):
			frappe.throw(
				f"Bench {self.bench} is not active. Please try again if you've deployed a new bench."
			)

		bench_group = frappe.db.get_value("Bench", self.bench, "group")
		if bench_group != self.group:
			frappe.throw(
				f"Bench release group {bench_group} is not the same as site release group {self.group}."
			)

		bench_server = frappe.db.get_value("Bench", self.bench, "server")
		if bench_server != self.server:
			frappe.throw(f"Bench server {bench_server} is not the same as site server {self.server}.")

	def validate_installed_apps(self):
		# validate apps to be installed on site
		bench_apps: Table[BenchApp] = frappe.get_doc("Bench", self.bench).apps
		for app in self.apps:
			if not find(bench_apps, lambda x: x.app == app.app):
				frappe.throw(f"app {app.app} is not available on Bench {self.bench}.")

		if self.apps[0].app != "frappe":
			frappe.throw("First app to be installed on site must be frappe.")

		site_apps = [app.app for app in self.apps]
		if len(site_apps) != len(set(site_apps)):
			frappe.throw("Can't install same app twice.")

		# Install apps in the same order as bench
		if self.is_new():
			self.sort_apps(bench_apps)

	def sort_apps(self, bench_apps: Table[BenchApp]):
		bench_app_names = [app.app for app in bench_apps]
		self.apps.sort(key=lambda x: bench_app_names.index(x.app))
		for idx, app in enumerate(self.apps):
			app.idx = idx + 1

	def validate_host_name(self):
		# set or update site.host_name
		if self.is_new():
			self.host_name = self.name
			self._update_configuration({"host_name": f"https://{self.host_name}"}, save=False)
		elif self.has_value_changed("host_name"):
			self._validate_host_name()

	def validate_site_config(self):
		# update site._keys_removed_in_last_update value
		old_keys = json.loads(self.config)
		new_keys = [x.key for x in self.configuration]
		self._keys_removed_in_last_update = json.dumps([x for x in old_keys if x not in new_keys])

		# generate site.config from site.configuration
		self.update_config_preview()

		# create an agent request if config has been updated
		# if not self.is_new() and self.has_value_changed("config"):
		# 	Agent(self.server).update_site_config(self)

	def validate_auto_update_fields(self):
		# Validate day of month
		if not (1 <= self.update_on_day_of_month <= 31):
			frappe.throw("Day of the month must be between 1 and 31 (included)!")
		# If site is on public bench, don't allow to disable auto updates
		is_group_public = frappe.get_cached_value("Release Group", self.group, "public")
		if self.skip_auto_updates and is_group_public:
			frappe.throw("Auto updates can't be disabled for sites on public benches!")

	def validate_site_plan(self):
		if hasattr(self, "subscription_plan") and self.subscription_plan:
			"""
			If `release_groups` in site plan is empty, then site can be deployed in any release group.
			Otherwise, site can only be deployed in the clusters mentioned in the release groups.
			"""
			release_groups = frappe.db.get_all(
				"Site Plan Release Group",
				pluck="release_group",
				filters={
					"parenttype": "Site Plan",
					"parentfield": "release_groups",
					"parent": self.subscription_plan,
				},
			)
			clusters = frappe.db.get_all("Bench", pluck="cluster", filters={"group": ("in", release_groups)})
			is_valid = len(clusters) == 0 or self.cluster in clusters
			if not is_valid:
				frappe.throw(f"In {self.subscription_plan}, you can't deploy site in {self.cluster} cluster")

			"""
			If `allowed_apps` in site plan is empty, then site can be deployed with any apps.
			Otherwise, site can only be deployed with the apps mentioned in the site plan.
			"""
			allowed_apps = frappe.db.get_all(
				"Site Plan Allowed App",
				pluck="app",
				filters={
					"parenttype": "Site Plan",
					"parentfield": "allowed_apps",
					"parent": self.subscription_plan,
				},
			)
			if allowed_apps:
				selected_apps = [app.app for app in self.apps]

				for app in selected_apps:
					if app not in allowed_apps:
						frappe.throw(f"In {self.subscription_plan}, you can't deploy site with {app} app")

			is_dedicated_server_plan = frappe.db.get_value(
				"Site Plan", self.subscription_plan, "dedicated_server_plan"
			)
			is_site_on_public_server = frappe.db.get_value("Server", self.server, "public")

			# If site is on public server, don't allow unlimited plans
			if is_site_on_public_server and is_dedicated_server_plan:
				self.subscription_plan = frappe.db.get_value(
					"Site Plan",
					{
						"private_benches": 1,
						"dedicated_server_plan": 0,
						"document_type": "Site",
						"price_inr": ["!=", 0],
					},
					order_by="price_inr asc",
				)

			# If site is on dedicated server, set unlimited plan
			elif not is_dedicated_server_plan and not is_site_on_public_server:
				self.subscription_plan = frappe.db.get_value(
					"Site Plan",
					{
						"dedicated_server_plan": 1,
						"document_type": "Site",
						"support_included": 0,
					},
				)

	def capture_signup_event(self, event: str):
		team = frappe.get_doc("Team", self.team)
		if frappe.db.count("Site", {"team": team.name}) <= 1 and team.account_request:
			from press.utils.telemetry import capture

			account_request = frappe.get_doc("Account Request", team.account_request)
			if not (account_request.is_saas_signup() or account_request.invited_by_parent_team):
				capture(event, "fc_signup", team.user)

	def on_update(self):
		if self.status == "Active" and self.has_value_changed("host_name"):
			self.update_site_config({"host_name": f"https://{self.host_name}"})
			self._update_redirects_for_all_site_domains()
			frappe.db.set_value("Site Domain", self.host_name, "redirect_to_primary", False)

		self.update_subscription()

		if self.has_value_changed("team"):
			frappe.db.set_value("Site Domain", {"site": self.name}, "team", self.team)
			frappe.db.delete("Press Role Permission", {"site": self.name})

		if self.status not in [
			"Pending",
			"Archived",
			"Suspended",
		] and (self.has_value_changed("subdomain") or self.has_value_changed("domain")):
			self.rename(self._get_site_name(self.subdomain))

		# Telemetry: Send event if first site status changed to Active
		if self.status == "Active" and self.has_value_changed("status"):
			self.capture_signup_event("first_site_status_changed_to_active")

		if self.has_value_changed("status"):
			create_site_status_update_webhook_event(self.name)

	def generate_saas_communication_secret(self, create_agent_job=False, save=True):
		if not self.standby_for and not self.standby_for_product:
			return
		if not self.saas_communication_secret:
			self.saas_communication_secret = frappe.generate_hash(length=32)
			config = {
				"fc_communication_secret": self.saas_communication_secret,
			}
			if create_agent_job:
				self.update_site_config(config)
			else:
				self._update_configuration(config=config, save=save)

	def rename_upstream(self, new_name: str):
		proxy_server = frappe.db.get_value("Server", self.server, "proxy_server")
		agent = Agent(proxy_server, server_type="Proxy Server")
		site_domains = frappe.get_all(
			"Site Domain", {"site": self.name, "name": ("!=", self.name)}, pluck="name"
		)
		agent.rename_upstream_site(self.server, self, new_name, site_domains)

	def set_apps(self, apps: list):
		self.apps = []
		bench_apps = frappe.get_doc("Bench", self.bench).apps
		for app in apps:
			if not find(bench_apps, lambda x: x.app == app):
				continue
			self.append("apps", {"app": app})
		self.save()

	@frappe.whitelist()
	def sync_apps(self):
		agent = Agent(self.server)
		apps_list = agent.get_site_apps(site=self)
		self.set_apps(apps_list)

	@frappe.whitelist()
	def retry_rename(self):
		"""Retry rename with current subdomain"""
		if self.name != self._get_site_name(self.subdomain):
			self.rename(self._get_site_name(self.subdomain))
		else:
			frappe.throw("Please choose a different subdomain")

	@frappe.whitelist()
	def retry_archive(self):
		"""Retry archive with subdomain+domain name of site"""
		site_name = self.subdomain + "." + self.domain
		if frappe.db.exists("Site", {"name": site_name, "bench": self.bench}):
			frappe.throw(f"Another site already exists in {self.bench} with name: {site_name}")
		self.archive(site_name=site_name, reason="Retry Archive")

	def check_duplicate_site(self):
		if frappe.db.exists(
			"Site",
			{
				"subdomain": self.subdomain,
				"domain": self.domain,
				"status": ("!=", "Archived"),
				"name": ("!=", self.name),
			},
		):
			frappe.throw("Site with same subdomain already exists")

	def rename(self, new_name: str):
		self.check_duplicate_site()
		create_dns_record(doc=self, record_name=self._get_site_name(self.subdomain))
		agent = Agent(self.server)
		if self.standby_for_product or self.standby_for:
			# if standby site, rename site and create first user for trial signup
			create_user = self.get_user_details()
			# update the subscription config while renaming the standby site
			self.update_config_preview()
			site_config = json.loads(self.config)
			subscription_config = site_config.get("subscription", {})
			job = agent.rename_site(self, new_name, create_user, config={"subscription": subscription_config})
			self.flags.rename_site_agent_job_name = job.name
		else:
			agent.rename_site(self, new_name)
		self.rename_upstream(new_name)
		self.status = "Pending"
		self.save()

		try:
			# remove old dns record from route53 after rename
			domain = frappe.get_doc("Root Domain", self.domain)
			proxy_server = frappe.get_value("Server", self.server, "proxy_server")
			self.remove_dns_record(domain, proxy_server, self.name)
		except Exception:
			log_error("Removing Old Site from Route53 Failed")

	def update_config_preview(self):
		"""Regenerates site.config on each site.validate from the site.configuration child table data"""
		new_config = {}

		# Update from site.configuration
		for row in self.configuration:
			# update internal flag from master
			row.internal = frappe.db.get_value("Site Config Key", row.key, "internal")
			key_type = row.type or row.get_type()
			row.type = key_type

			if key_type == "Number":
				key_value = int(row.value) if isinstance(row.value, (float, int)) else json.loads(row.value)
			elif key_type == "Boolean":
				key_value = (
					row.value if isinstance(row.value, bool) else bool(sbool(json.loads(cstr(row.value))))
				)
			elif key_type == "JSON":
				key_value = json.loads(cstr(row.value))
			else:
				key_value = row.value

			new_config[row.key] = key_value

		self.config = json.dumps(new_config, indent=4)

	def install_marketplace_conf(self, app: str, plan: str | None = None):
		if plan:
			MarketplaceAppPlan.create_marketplace_app_subscription(self.name, app, plan, self.team)
		marketplace_app_hook(app=app, site=self, op="install")

	def uninstall_marketplace_conf(self, app: str):
		marketplace_app_hook(app=app, site=self, op="uninstall")

		# disable marketplace plan if it exists
		marketplace_app_name = frappe.db.get_value("Marketplace App", {"app": app})
		app_subscription = frappe.db.exists(
			"Subscription",
			{
				"team": self.team,
				"site": self.name,
				"document_type": "Marketplace App",
				"document_name": marketplace_app_name,
			},
		)
		if marketplace_app_name and app_subscription:
			frappe.db.set_value("Subscription", app_subscription, "enabled", 0)

	def check_marketplace_app_installable(self, plan: str | None = None):
		if not plan:
			return
		if (
			not frappe.db.get_value("Marketplace App Plan", plan, "price_usd") <= 0
			and not frappe.local.team().can_install_paid_apps()
		):
			frappe.throw(
				"You cannot install a Paid app on Free Credits. Please buy credits before trying to install again."
			)

			# TODO: check if app is available and can be installed

	@dashboard_whitelist()
	@site_action(["Active"])
	def install_app(self, app: str, plan: str | None = None) -> str:
		self.check_marketplace_app_installable(plan)

		if find(self.apps, lambda x: x.app == app):
			return None

		agent = Agent(self.server)
		job = agent.install_app_site(self, app)
		log_site_activity(self.name, "Install App", app, job.name)
		self.status = "Pending"
		self.save()
		self.install_marketplace_conf(app, plan)

		return job.name

	@dashboard_whitelist()
	@site_action(["Active"])
	def uninstall_app(self, app: str) -> str:
		agent = Agent(self.server)
		job = agent.uninstall_app_site(self, app)

		log_site_activity(self.name, "Uninstall App", app, job.name)

		self.uninstall_marketplace_conf(app)
		self.status = "Pending"
		self.save()

		return job.name

	def _create_default_site_domain(self):
		"""Create Site Domain with Site name."""
		return frappe.get_doc(
			{
				"doctype": "Site Domain",
				"site": self.name,
				"domain": self.name,
				"status": "Active",
				"retry_count": 0,
				"dns_type": "CNAME",
			}
		).insert(ignore_if_duplicate=True)

	def after_insert(self):
		from press.press.doctype.press_role.press_role import (
			add_permission_for_newly_created_doc,
		)

		self.capture_signup_event("created_first_site")

		if hasattr(self, "subscription_plan") and self.subscription_plan:
			# create subscription
			self.create_subscription(self.subscription_plan)
			self.reload()

		if hasattr(self, "app_plans") and self.app_plans:
			for app, plan in self.app_plans.items():
				MarketplaceAppPlan.create_marketplace_app_subscription(
					self.name, app, plan["name"], self.team, True
				)

		# log activity
		log_site_activity(self.name, "Create")
		self._create_default_site_domain()
		create_dns_record(self, record_name=self._get_site_name(self.subdomain))
		# self.create_agent_request()

		if hasattr(self, "share_details_consent") and self.share_details_consent:
			# create partner lead
			frappe.get_doc(doctype="Partner Lead", team=self.team, site=self.name).insert(
				ignore_permissions=True
			)

		if self.backup_time:
			self.backup_time = None  # because FF by default sets it to current time
			self.save()
		add_permission_for_newly_created_doc(self)

		create_site_status_update_webhook_event(self.name)

	def remove_dns_record(self, domain: Document, proxy_server: str, site: str):
		"""Remove dns record of site pointing to proxy."""
		_change_dns_record(method="DELETE", domain=domain, proxy_server=proxy_server, record_name=site)

	def is_version_14_or_higher(self) -> bool:
		group: ReleaseGroup = frappe.get_cached_doc("Release Group", self.group)
		return group.is_version_14_or_higher()

	@property
	def space_required_on_app_server(self):
		db_size, public_size, private_size = (
			frappe.get_doc("Remote File", file_name).size if file_name else 0
			for file_name in (
				self.remote_database_file,
				self.remote_public_file,
				self.remote_private_file,
			)
		)
		space_for_download = db_size + public_size + private_size
		space_for_extracted_files = (
			(0 if self.is_version_14_or_higher() else (8 * db_size)) + public_size + private_size
		)  # 8 times db size for extraction; estimated
		return space_for_download + space_for_extracted_files

	@property
	def space_required_on_db_server(self):
		db_size = frappe.get_doc("Remote File", self.remote_database_file).size
		return 8 * db_size * 2  # double extracted size for binlog

	def check_and_increase_disk(self, server: "BaseServer", space_required: int):
		mountpoint = server.guess_data_disk_mountpoint()
		free_space = server.free_space(mountpoint)
		if (diff := free_space - space_required) <= 0:
			msg = f"Insufficient estimated space on {DOCTYPE_SERVER_TYPE_MAP[server.doctype]} server to create site. Required: {human_readable(space_required)}, Available: {human_readable(free_space)} (Need {human_readable(abs(diff))})."
			if server.public:
				self.try_increasing_disk(server, mountpoint, diff, msg)
			else:
				frappe.throw(msg, InsufficientSpaceOnServer)

	def try_increasing_disk(self, server: "BaseServer", mountpoint: str, diff: int, err_msg: str):
		try:
			server.calculated_increase_disk_size(mountpoint=mountpoint, additional=diff / 1024 / 1024 // 1024)
		except VolumeResizeLimitError:
			frappe.throw(
				f"{err_msg} Please wait {fmt_timedelta(server.time_to_wait_before_updating_volume)} before trying again.",
				InsufficientSpaceOnServer,
			)

	def check_enough_space_on_server(self):
		app: "Server" = frappe.get_doc("Server", self.server)
		self.check_and_increase_disk(app, self.space_required_on_app_server)

		if app.database_server:
			db: "DatabaseServer" = frappe.get_doc("Database Server", app.database_server)
			self.check_and_increase_disk(db, self.space_required_on_db_server)

	def create_agent_request(self):
		agent = Agent(self.server)
		if self.remote_database_file:
			agent.new_site_from_backup(self, skip_failing_patches=self.skip_failing_patches)
		else:
			"""
			If the site is creating for saas / product trial purpose,
			Create a system user with password at the time of site creation.

			If `ignore_additional_system_user_creation` is set, don't create additional system user
			"""
			if (self.standby_for_product or self.standby_for) and not self.is_standby:
				user_details = self.get_user_details()
				if self.flags.get("ignore_additional_system_user_creation", False):
					user_details = None
				self.flags.new_site_agent_job_name = agent.new_site(self, create_user=user_details).name
			else:
				self.flags.new_site_agent_job_name = agent.new_site(self).name

		server = frappe.get_all("Server", filters={"name": self.server}, fields=["proxy_server"], limit=1)[0]

		agent = Agent(server.proxy_server, server_type="Proxy Server")
		agent.new_upstream_file(server=self.server, site=self.name)

	@dashboard_whitelist()
	@site_action(["Active", "Broken"])
	def reinstall(self):
		agent = Agent(self.server)
		job = agent.reinstall_site(self)
		log_site_activity(self.name, "Reinstall", job=job.name)
		self.status = "Pending"
		self.save()
		return job.name

	@dashboard_whitelist()
	@site_action(["Active", "Broken"])
	def migrate(self, skip_failing_patches=False):
		agent = Agent(self.server)
		activate = True
		if self.status in ("Inactive", "Suspended"):
			activate = False
			self.status_before_update = self.status
		elif self.status == "Broken" and self.status_before_update in (
			"Inactive",
			"Suspended",
		):
			activate = False
		job = agent.migrate_site(self, skip_failing_patches=skip_failing_patches, activate=activate)
		log_site_activity(self.name, "Migrate", job=job.name)
		self.status = "Pending"
		self.save()

	@frappe.whitelist()
	def last_migrate_failed(self):
		"""Returns `True` if the last site update's(`Migrate` deploy type) migrate site job step failed, `False` otherwise"""

		site_update = frappe.get_all(
			"Site Update",
			filters={"site": self.name},
			fields=["status", "update_job", "deploy_type"],
			limit=1,
			order_by="creation desc",
		)

		if not (site_update and site_update[0].deploy_type == "Migrate"):
			return False
		site_update = site_update[0]

		if site_update.status == "Recovered":
			migrate_site_step = frappe.get_all(
				"Agent Job Step",
				filters={
					"step_name": "Migrate Site",
					"agent_job": site_update.update_job,
				},
				fields=["status"],
				limit=1,
			)

			if migrate_site_step and migrate_site_step[0].status == "Failure":
				return True

		return False

	@frappe.whitelist()
	def restore_tables(self):
		self.status_before_update = self.status
		agent = Agent(self.server)
		agent.restore_site_tables(self)
		self.status = "Pending"
		self.save()

	@dashboard_whitelist()
	def clear_site_cache(self):
		agent = Agent(self.server)
		job = agent.clear_site_cache(self)

		log_site_activity(self.name, "Clear Cache", job=job.name)

	@dashboard_whitelist()
	@site_action(["Active", "Broken"])
	def restore_site(self, skip_failing_patches=False):
		frappe.enqueue(self._restore_site, queue="long", job_name=f"restore_site_{self.name}", timeout=3600, at_front=True)
		self.status = "Pending"
		self.save()
		return self.name

	def _restore_site(self):
		backup_job = BackupRestore(self)
		backup_job.execute()

	@dashboard_whitelist()
	@site_action(["Active", "Broken"])
	def restore_site_from_files(self, files, skip_failing_patches=False):
		self.remote_database_file = files["database"]
		self.remote_public_file = files["public"]
		self.remote_private_file = files["private"]
		self.save()
		self.reload()
		return self.restore_site(skip_failing_patches=skip_failing_patches)

	@dashboard_whitelist()
	def backup(self, with_files=False, offsite=False, force=False):
		if self.status == "Suspended":
			activity = frappe.db.get_all(
				"Site Activity",
				filters={"site": self.name, "action": "Suspend Site"},
				order_by="creation desc",
				limit=1,
			)
			suspension_time = frappe.get_doc("Site Activity", activity[0]).creation

			if (
				frappe.db.count(
					"Site Backup",
					filters=dict(
						site=self.name,
						status="Success",
						creation=(">=", suspension_time),
					),
				)
				> 3
			):
				frappe.throw("You cannot take more than 3 backups after site suspension")

		return frappe.get_doc(
			{
				"doctype": "Site Backup",
				"site": self.name,
				"with_files": with_files,
				"offsite": offsite,
				"force": force,
			}
		).insert()

	@dashboard_whitelist()
	def get_backup_download_link(self, backup, file):
		from botocore.exceptions import ClientError

		if file not in ["database", "public", "private", "config_file"]:
			frappe.throw("Invalid file type")

		try:
			remote_file = frappe.db.get_value(
				"Site Backup",
				{"name": backup, "site": self.name},
				f"{file}_url",
			)
			return remote_file
		except ClientError:
			log_error(title="Offsite Backup Response Exception")

	def site_migration_scheduled(self):
		return frappe.db.get_value(
			"Site Migration", {"site": self.name, "status": "Scheduled"}, "scheduled_time"
		)

	def site_update_scheduled(self):
		return frappe.db.get_value(
			"Site Update", {"site": self.name, "status": "Scheduled"}, "scheduled_time"
		)

	def check_move_scheduled(self):
		if time := self.site_migration_scheduled():
			frappe.throw(f"Site Migration is scheduled for {self.name} at {time}")
		if time := self.site_update_scheduled():
			frappe.throw(f"Site Update is scheduled for {self.name} at {time}")

	def ready_for_move(self):
		if self.status in ["Updating", "Pending", "Installing"]:
			frappe.throw(f"Site is in {self.status} state. Cannot Update", SiteUnderMaintenance)
		elif self.status == "Archived":
			frappe.throw("Site is archived. Cannot Update", SiteAlreadyArchived)
		self.check_move_scheduled()

		self.status_before_update = self.status
		self.status = "Pending"
		self.save()

	@dashboard_whitelist()
	@site_action(["Active", "Inactive", "Suspended"])
	def schedule_update(
		self,
		skip_failing_patches: bool = False,
		skip_backups: bool = False,
		scheduled_time: str | None = None,
	):
		log_site_activity(self.name, "Update")

		doc = frappe.get_doc(
			{
				"doctype": "Site Update",
				"site": self.name,
				"skipped_failing_patches": skip_failing_patches,
				"skipped_backups": skip_backups,
				"status": "Scheduled" if scheduled_time else "Pending",
				"scheduled_time": scheduled_time,
			}
		).insert()
		return doc.name

	@dashboard_whitelist()
	def edit_scheduled_update(
		self,
		name,
		skip_failing_patches: bool = False,
		skip_backups: bool = False,
		scheduled_time: str | None = None,
	):
		doc = frappe.get_doc("Site Update", name)
		doc.skipped_failing_patches = skip_failing_patches
		doc.skipped_backups = skip_backups
		doc.scheduled_time = scheduled_time
		doc.save()
		return doc.name

	@dashboard_whitelist()
	def cancel_scheduled_update(self, site_update: str):
		if status := frappe.db.get_value("Site Update", site_update, "status") != "Scheduled":
			frappe.throw(f"Cannot cancel a Site Update with status {status}")

		# TODO: Set status to cancelled instead of deleting the doc
		frappe.delete_doc("Site Update", site_update)

	@frappe.whitelist()
	def move_to_group(self, group, skip_failing_patches=False, skip_backups=False):
		log_site_activity(self.name, "Update")

		return frappe.get_doc(
			{
				"doctype": "Site Update",
				"site": self.name,
				"destination_group": group,
				"skipped_failing_patches": skip_failing_patches,
				"skipped_backups": skip_backups,
				"ignore_past_failures": True,
			}
		).insert()

	@frappe.whitelist()
	def move_to_bench(self, bench, deactivate=True, skip_failing_patches=False):
		frappe.only_for("System Manager")
		self.ready_for_move()

		if bench == self.bench:
			frappe.throw("Site is already on the selected bench.")

		agent = Agent(self.server)
		job = agent.move_site_to_bench(self, bench, deactivate, skip_failing_patches)
		log_site_activity(self.name, "Update", job=job.name)

		return job

	def reset_previous_status(self, fix_broken=False):
		if self.status == "Archived":
			return
		self.status = self.status_before_update
		self.status_before_update = None
		if not self.status or (self.status == "Broken" and fix_broken):
			status_map = {402: "Suspended", 503: "Inactive"}
			try:
				response = requests.get(f"https://{self.name}")
				self.status = status_map.get(response.status_code, "Active")
			except Exception:
				log_error("Site Status Fetch Error", site=self.name)
		self.save()

	@frappe.whitelist()
	@site_action(["Active"])
	def update_without_backup(self):
		log_site_activity(self.name, "Update")

		frappe.get_doc(
			{
				"doctype": "Site Update",
				"site": self.name,
				"skipped_backups": 1,
			}
		).insert()

	@dashboard_whitelist()
	def add_domain(self, domain):
		domain = domain.lower().strip(".")
		response = check_dns(self.name, domain)
		if response["matched"]:
			log_site_activity(self.name, "Add Domain")
			frappe.get_doc(
				{
					"doctype": "Site Domain",
					"status": "Pending",
					"site": self.name,
					"domain": domain,
					"dns_type": response["type"],
					"dns_response": json.dumps(response, indent=4, default=str),
				}
			).insert()

	@frappe.whitelist()
	def create_dns_record(self):
		create_dns_record(doc=self, record_name=self._get_site_name(self.subdomain))

	@frappe.whitelist()
	def update_dns_record(self, value):
		domain = frappe.get_doc("Root Domain", self.domain)
		record_name = self._get_site_name(self.subdomain)
		_change_dns_record("UPSERT", domain, value, record_name)

	def get_config_value_for_key(self, key: str) -> Any:
		"""
		Get site config value configuration child table for given key.

		:returns: None if key not in config.
		"""
		key_obj = find(self.configuration, lambda x: x.key == key)
		if key_obj:
			return json.loads(key_obj.get("value"))
		return None

	def add_domain_to_config(self, domain: str):
		domains = self.get_config_value_for_key("domains") or []
		domains.append(domain)
		self._update_configuration({"domains": domains})
		agent = Agent(self.server)
		agent.add_domain(self, domain)

	def remove_domain_from_config(self, domain):
		domains = self.get_config_value_for_key("domains") or []
		if domain not in domains:
			return
		domains.remove(domain)
		self._update_configuration({"domains": domains})
		agent = Agent(self.server)
		agent.remove_domain(self, domain)

	@dashboard_whitelist()
	def remove_domain(self, domain):
		if domain == self.name:
			frappe.throw("Cannot delete default site_domain")
		site_domain = frappe.get_all("Site Domain", filters={"site": self.name, "domain": domain})[0]
		site_domain = frappe.delete_doc("Site Domain", site_domain.name)

	def retry_add_domain(self, domain):
		if check_dns(self.name, domain)["matched"]:
			site_domain = frappe.get_all(
				"Site Domain",
				filters={
					"site": self.name,
					"domain": domain,
					"status": ("!=", "Active"),
					"retry_count": ("<=", 5),
				},
			)[0]
			site_domain = frappe.get_doc("Site Domain", site_domain.name)
			site_domain.retry()

	def _check_if_domain_belongs_to_site(self, domain: str):
		if not frappe.db.exists({"doctype": "Site Domain", "site": self.name, "domain": domain}):
			frappe.throw(
				msg=f"Site Domain {domain} for site {self.name} does not exist",
				exc=frappe.exceptions.LinkValidationError,
			)

	def _check_if_domain_is_active(self, domain: str):
		status = frappe.get_value("Site Domain", domain, "status")
		if status != "Active":
			frappe.throw(msg="Only active domains can be primary", exc=frappe.LinkValidationError)

	def _validate_host_name(self):
		"""Perform checks for primary domain."""
		self._check_if_domain_belongs_to_site(self.host_name)
		self._check_if_domain_is_active(self.host_name)

	@dashboard_whitelist()
	def set_host_name(self, domain: str):
		"""Set host_name/primary domain of site."""
		self.host_name = domain
		self.save()

	def _get_redirected_domains(self) -> list[str]:
		"""Get list of redirected site domains for site."""
		return frappe.get_all(
			"Site Domain",
			filters={"site": self.name, "redirect_to_primary": True},
			pluck="name",
		)

	def _update_redirects_for_all_site_domains(self):
		domains = self._get_redirected_domains()
		if domains:
			return self.set_redirects_in_proxy(domains)
		return None

	def _remove_redirects_for_all_site_domains(self):
		domains = self._get_redirected_domains()
		if domains:
			self.unset_redirects_in_proxy(domains)

	def set_redirects_in_proxy(self, domains: list[str]):
		target = self.host_name
		proxy_server = frappe.db.get_value("Server", self.server, "proxy_server")
		agent = Agent(proxy_server, server_type="Proxy Server")
		return agent.setup_redirects(self.name, domains, target)

	def unset_redirects_in_proxy(self, domains: list[str]):
		proxy_server = frappe.db.get_value("Server", self.server, "proxy_server")
		agent = Agent(proxy_server, server_type="Proxy Server")
		agent.remove_redirects(self.name, domains)

	@dashboard_whitelist()
	def set_redirect(self, domain: str):
		"""Enable redirect to primary for domain."""
		self._check_if_domain_belongs_to_site(domain)
		site_domain = frappe.get_doc("Site Domain", domain)
		site_domain.setup_redirect()

	@dashboard_whitelist()
	def unset_redirect(self, domain: str):
		"""Disable redirect to primary for domain."""
		self._check_if_domain_belongs_to_site(domain)
		site_domain = frappe.get_doc("Site Domain", domain)
		site_domain.remove_redirect()

	@dashboard_whitelist()
	@site_action(["Active", "Broken", "Suspended"])
	def archive(self, site_name=None, reason=None, force=False, skip_reload=False):
		agent = Agent(self.server)
		self.status = "Pending"
		self.save()
		job = agent.archive_site(self, site_name, force)
		log_site_activity(self.name, "Archive", reason, job.name)

		server = frappe.get_all("Server", filters={"name": self.server}, fields=["proxy_server"], limit=1)[0]

		agent = Agent(server.proxy_server, server_type="Proxy Server")
		agent.remove_upstream_file(
			server=self.server,
			site=self.name,
			site_name=site_name,
			skip_reload=skip_reload,
		)

		self.db_set("host_name", None)

		self.delete_offsite_backups()
		frappe.db.set_value(
			"Site Backup",
			{"site": self.name, "offsite": False},
			"files_availability",
			"Unavailable",
		)
		self.disable_subscription()
		self.disable_marketplace_subscriptions()

		self.archive_site_database_users()

	@frappe.whitelist()
	def cleanup_after_archive(self):
		site_cleanup_after_archive(self.name)

	def delete_offsite_backups(self):
		from press.press.doctype.remote_file.remote_file import (
			delete_remote_backup_objects,
		)

		log_site_activity(self.name, "Drop Offsite Backups")

		sites_remote_files = []
		site_backups = frappe.get_all(
			"Site Backup",
			filters={
				"site": self.name,
				"offsite": True,
				"files_availability": "Available",
			},
			pluck="name",
			order_by="creation desc",
		)[1:]  # Keep latest backup
		for backup_files in frappe.get_all(
			"Site Backup",
			filters={"name": ("in", site_backups)},
			fields=[
				"remote_database_file",
				"remote_public_file",
				"remote_private_file",
			],
			as_list=True,
			order_by="creation desc",
			ignore_ifnull=True,
		):
			sites_remote_files += backup_files

		if not sites_remote_files:
			return None

		frappe.db.set_value(
			"Site Backup",
			{"name": ("in", site_backups), "offsite": True},
			"files_availability",
			"Unavailable",
		)

		return delete_remote_backup_objects(sites_remote_files)

	@dashboard_whitelist()
	def send_change_team_request(self, team_mail_id: str, reason: str):
		"""Send email to team to accept site transfer request"""

		if self.team != get_current_team():
			frappe.throw(
				"You should belong to the team owning the site to initiate a site ownership transfer."
			)

		if not frappe.db.exists("Team", {"user": team_mail_id, "enabled": 1}):
			frappe.throw("No Active Team record found.")

		old_team = frappe.db.get_value("Team", self.team, "user")

		if old_team == team_mail_id:
			frappe.throw(f"Site is already owned by the team {team_mail_id}")

		key = frappe.generate_hash("Site Transfer Link", 20)
		frappe.get_doc(
			{
				"doctype": "Team Change",
				"document_type": "Site",
				"document_name": self.name,
				"to_team": frappe.db.get_value("Team", {"user": team_mail_id}),
				"from_team": self.team,
				"reason": reason,
				"key": key,
			}
		).insert()

		link = get_url(f"/api/method/press.api.site.confirm_site_transfer?key={key}")

		if frappe.conf.developer_mode:
			print(f"\nSite transfer link for {team_mail_id}\n{link}\n")

		frappe.sendmail(
			recipients=team_mail_id,
			subject="Transfer Site Ownership Confirmation",
			template="transfer_team_confirmation",
			args={
				"name": self.host_name or self.name,
				"type": "site",
				"old_team": old_team,
				"new_team": team_mail_id,
				"transfer_url": link,
			},
		)

	@dashboard_whitelist()
	@site_action(["Active"])
	def login_as_admin(self, reason=None):
		sid = self.login(reason=reason)
		return f"https://{self.host_name or self.name}/desk?sid={sid}"

	@dashboard_whitelist()
	@site_action(["Active"])
	def login_as_team(self, reason=None):
		if self.additional_system_user_created:
			team_user = frappe.db.get_value("Team", self.team, "user")
			sid = self.get_login_sid(user=team_user)
			return f"https://{self.host_name or self.name}/desk?sid={sid}"

		frappe.throw("No additional system user created for this site")
		return None

	@frappe.whitelist()
	def login(self, reason=None):
		log_site_activity(self.name, "Login as Administrator", reason=reason)
		return self.get_login_sid()

	def create_user_with_team_info(self):
		team_user = frappe.db.get_value("Team", self.team, "user")
		user = frappe.get_doc("User", team_user)
		return self.create_user(user.email, user.first_name or "", user.last_name or "")

	def create_user(self, email, first_name, last_name, password=None):
		if self.additional_system_user_created:
			return None
		agent = Agent(self.server)
		return agent.create_user(self, email, first_name, last_name, password)

	@frappe.whitelist()
	def show_admin_password(self):
		frappe.msgprint(self.get_password("admin_password"), title="Password", indicator="green")

	def get_connection_as_admin(self):
		password = get_decrypted_password("Site", self.name, "admin_password")
		return FrappeClient(f"https://{self.name}", "Administrator", password)

	def get_login_sid(self, user="Administrator"):
		sid = None
		if user == "Administrator":
			password = get_decrypted_password("Site", self.name, "admin_password")
			response = requests.post(
				f"https://{self.name}/api/method/login",
				data={"usr": "Administrator", "pwd": password},
			)
			sid = response.cookies.get("sid")
		if not sid:
			try:
				agent = Agent(self.server)
				sid = agent.get_site_sid(self, user)
			except AgentRequestSkippedException:
				frappe.throw(
					"Server is unresponsive. Please try again in some time.",
					frappe.ValidationError,
				)
		if not sid or sid == "Guest":
			frappe.throw(f"Could not login as {user}", frappe.ValidationError)
		return sid

	def fetch_info(self):
		agent = Agent(self.server)
		return agent.get_site_info(self)

	def fetch_analytics(self):
		agent = Agent(self.server)
		if agent.should_skip_requests():
			return None
		return agent.get_site_analytics(self)

	def get_disk_usages(self):
		try:
			last_usage = frappe.get_last_doc("Site Usage", {"site": self.name})
		except frappe.DoesNotExistError:
			return defaultdict(lambda: None)

		return {
			"database": last_usage.database,
			"database_free": last_usage.database_free,
			"backups": last_usage.backups,
			"public": last_usage.public,
			"private": last_usage.private,
			"creation": last_usage.creation,
		}

	def _sync_config_info(self, fetched_config: dict) -> bool:
		"""Update site doc config with the fetched_config values.

		:fetched_config: Generally data passed is the config part of the agent info response
		:returns: True if value has changed
		"""
		config = {
			key: fetched_config[key] for key in fetched_config if key not in get_client_blacklisted_keys()
		}
		new_config = {**json.loads(self.config or "{}"), **config}
		current_config = json.dumps(new_config, indent=4)

		if self.config != current_config:
			self._update_configuration(new_config, save=False)
			return True
		return False

	def _sync_usage_info(self, fetched_usage: dict):
		"""Generate a Site Usage doc for the site using the fetched_usage data.

		:fetched_usage: Requires backups, database, public, private keys with Numeric values
		"""

		if isinstance(fetched_usage, list):
			for usage in fetched_usage:
				self._insert_site_usage(usage)
		else:
			self._insert_site_usage(fetched_usage)

	def _insert_site_usage(self, usage: dict):
		current_usages = self.get_disk_usages()
		site_usage_data = {
			"site": self.name,
			"backups": usage["backups"],
			"database": usage["database"],
			"database_free": usage.get("database_free", 0),
			"database_free_tables": json.dumps(usage.get("database_free_tables", []), indent=1),
			"public": usage["public"],
			"private": usage["private"],
		}

		same_as_last_usage = (
			current_usages["backups"] == site_usage_data["backups"]
			and current_usages["database"] == site_usage_data["database"]
			and current_usages["public"] == site_usage_data["public"]
			and current_usages["private"] == site_usage_data["private"]
			and current_usages["database_free"] == site_usage_data["private"]
		)

		if same_as_last_usage:
			return

		equivalent_site_time = None
		if usage.get("timestamp"):
			equivalent_site_time = convert_utc_to_user_timezone(
				dateutil.parser.parse(usage["timestamp"])
			).replace(tzinfo=None)
			if frappe.db.exists("Site Usage", {"site": self.name, "creation": equivalent_site_time}):
				return
			if current_usages["creation"] and equivalent_site_time < current_usages["creation"]:
				return

		site_usage = frappe.get_doc({"doctype": "Site Usage", **site_usage_data}).insert()

		if equivalent_site_time:
			site_usage.db_set("creation", equivalent_site_time)

	def _sync_timezone_info(self, timezone: str) -> bool:
		"""Update site doc timezone with the passed value of timezone.

		:timezone: Timezone passed in part of the agent info response
		:returns: True if value has changed
		"""
		# Validate timezone string
		# Empty string is fine, since we default to IST
		if timezone:
			try:
				pytz.timezone(timezone)
			except pytz.exceptions.UnknownTimeZoneError:
				return False

		if self.timezone != timezone:
			self.timezone = timezone
			return True
		return False

	def _sync_database_name(self, config):
		database_name = config.get("db_name")
		if self.database_name != database_name:
			self.database_name = database_name
			return True
		return False

	@frappe.whitelist()
	def sync_info(self, data=None):
		"""Updates Site Usage, site.config and timezone details for site."""
		if not data:
			data = self.fetch_info()

		if not data:
			return

		fetched_usage = data["usage"]
		fetched_config = data["config"]
		fetched_timezone = data["timezone"]

		self._sync_usage_info(fetched_usage)
		to_save = self._sync_config_info(fetched_config)
		to_save |= self._sync_timezone_info(fetched_timezone)
		to_save |= self._sync_database_name(fetched_config)

		if to_save:
			self.save()

	def sync_analytics(self, analytics=None):
		if not analytics:
			analytics = self.fetch_analytics()
		if analytics:
			create_site_analytics(self.name, analytics)

	@dashboard_whitelist()
	def is_setup_wizard_complete(self):
		if self.setup_wizard_complete:
			return True

		sid = self.get_login_sid()
		conn = FrappeClient(f"https://{self.name}?sid={sid}")

		try:
			value = conn.get_value("System Settings", "setup_complete", "System Settings")
		except json.JSONDecodeError:
			# the proxy might be down or network failure
			# that's why the response is blank and get_value try to parse the json
			# and raise json.JSONDecodeError
			return False
		except Exception:
			if self.ping().status_code == requests.codes.ok:
				# Site is up but setup status fetch failed
				log_error("Fetching Setup Status Failed", doc=self)
			return False

		setup_complete = cint(value["setup_complete"])
		if not setup_complete:
			return False

		self.reload()
		self.setup_wizard_complete = 1

		self.team = (
			frappe.db.get_value(
				"Team",
				{"user": frappe.db.get_value("Account Request", self.account_request, "email")},
				"name",
			)
			if self.team == "Administrator"
			else self.team
		)

		self.save()

		# Telemetry: Send event if first site status changed to Active
		if self.setup_wizard_complete:
			self.capture_signup_event("first_site_setup_wizard_completed")

		return setup_complete

	def fetch_setup_wizard_complete_status(self):
		with suppress(Exception):
			# max retries = 18, backoff time = 10s, with exponential backoff it will try for 30 days
			if self.setup_wizard_status_check_retries >= 18:
				return
			is_completed = self.is_setup_wizard_complete()
			if not is_completed:
				self.setup_wizard_status_check_retries += 1
				exponential_backoff_duration = 10 * (2**self.setup_wizard_status_check_retries)
				self.setup_wizard_status_check_next_retry_on = add_to_date(
					now_datetime(), seconds=exponential_backoff_duration
				)
				self.save()

	@frappe.whitelist()
	def set_status_based_on_ping(self):
		if self.status in ("Active", "Archived", "Inactive", "Suspended"):
			return
		try:
			response = self.ping()
		except Exception:
			return
		else:
			if response.status_code == requests.codes.ok:
				self.status = "Active"
				self.save()

	def ping(self):
		return requests.get(f"https://{self.name}/api/method/ping")

	def _set_configuration(self, config: list[dict]):
		"""Similar to _update_configuration but will replace full configuration at once
		This is necessary because when you update site config from the UI, you can update the key,
		update the value, remove the key. All of this can be handled by setting the full configuration at once.

		Args:
		config (list): List of dicts with key, value, and type
		"""
		blacklisted_config = [x for x in self.configuration if x.key in get_client_blacklisted_keys()]
		self.configuration = []

		# Maintain keys that aren't accessible to Dashboard user
		for i, _config in enumerate(blacklisted_config):
			_config.idx = i + 1
			self.configuration.append(_config)

		for d in config:
			d = frappe._dict(d)
			if isinstance(d.value, (dict, list)):
				value = json.dumps(d.value)
			else:
				value = d.value
			# Value is mandatory, skip None and empty strings
			if value is None or cstr(value).strip() == "":
				continue
			self.append("configuration", {"key": d.key, "value": value, "type": d.type})
		self.save()

	def _update_configuration(self, config, save=True):
		"""Updates site.configuration, runs site.save which updates site.config

		Args:
		config (dict): Python dict for any suitable frappe.conf
		"""
		existing_keys = {x.key: i for i, x in enumerate(self.configuration)}
		for key, value in config.items():
			_type = frappe.get_value("Site Config Key", {"key": key}, "type") or guess_type(value)
			converted_value = convert(value)
			if converted_value is None or cstr(converted_value).strip() == "":
				continue
			if key in existing_keys:
				self.configuration[existing_keys[key]].value = converted_value
				self.configuration[existing_keys[key]].type = _type
			else:
				self.append(
					"configuration",
					{"key": key, "value": converted_value, "type": _type},
				)

		if save:
			self.save()

	@dashboard_whitelist()
	@site_action(["Active"])
	def update_config(self, config=None):
		"""Updates site.configuration, meant for dashboard and API users"""
		if config is None:
			return
		# config = {"key1": value1, "key2": value2}
		config = frappe.parse_json(config)

		sanitized_config = {}
		for key, value in config.items():
			if key in get_client_blacklisted_keys():
				frappe.throw(_(f"The key <b>{key}</b> is blacklisted or internal and cannot be updated"))

			_type = self._site_config_key_type(key, value)

			if _type == "Number":
				value = flt(value)
			elif _type == "Boolean":
				value = bool(sbool(value))
			elif _type == "JSON":
				value = frappe.parse_json(value)
			elif _type == "Password" and value == "*******":
				value = frappe.get_value("Site Config", {"key": key, "parent": self.name}, "value")
			sanitized_config[key] = value

		self.update_site_config(sanitized_config)

	def _site_config_key_type(self, key, value):
		if frappe.db.exists("Site Config Key", key):
			return frappe.db.get_value("Site Config Key", key, "type")

		if isinstance(value, (dict, list)):
			return "JSON"
		if isinstance(value, bool):
			return "Boolean"
		if isinstance(value, (int, float)):
			return "Number"
		return "String"

	@dashboard_whitelist()
	@site_action(["Active"])
	def delete_config(self, key):
		"""Deletes a key from site configuration, meant for dashboard and API users"""
		if key in get_client_blacklisted_keys():
			return None

		updated_config = []
		for row in self.configuration:
			if row.key != key and not row.internal:
				updated_config.append({"key": row.key, "value": row.value, "type": row.type})

		return self.update_site_config(updated_config)

	def delete_multiple_config(self, keys: list[str]):
		# relies on self._keys_removed_in_last_update in self.validate
		# used by https://frappecloud.com/app/marketplace-app/email_delivery_service
		config_list: list[dict] = []
		for key in self.configuration:
			config = {}
			if key.key in keys:
				continue
			config["key"] = key.key
			config["value"] = key.value
			config["type"] = key.type
			config_list.append(config)
		self.update_site_config(config_list)

	@frappe.whitelist()
	def update_site_config(self, config=None):
		"""Updates site.configuration, site.config and runs site.save which initiates an Agent Request
		This checks for the blacklisted config keys via Frappe Validations, but not for internal usages.
		Don't expose this directly to an external API. Pass through `press.utils.sanitize_config` or use
		`press.api.site.update_config` instead.

		Args:
		config (dict): Python dict for any suitable frappe.conf
		"""
		if config is None:
			config = {}
		if isinstance(config, list):
			self._set_configuration(config)
		else:
			self._update_configuration(config)
		return Agent(self.server).update_site_config(self)

	def update_site(self):
		log_site_activity(self.name, "Update")

	def create_subscription(self, plan):
		# create a site plan change log
		self._create_initial_site_plan_change(plan)

	def update_subscription(self):
		if self.status in ["Archived", "Broken", "Suspended"]:
			self.disable_subscription()
		else:
			self.enable_subscription()

		if self.has_value_changed("team"):
			subscription = self.subscription
			if subscription:
				subscription.team = self.team
				subscription.save(ignore_permissions=True)

	def enable_subscription(self):
		subscription = self.subscription
		if subscription:
			subscription.enable()

	def disable_subscription(self):
		subscription = self.subscription
		if subscription:
			frappe.db.set_value("Subscription", subscription.name, "enabled", False)

	def disable_marketplace_subscriptions(self):
		app_subscriptions = frappe.get_all(
			"Marketplace App Subscription",
			filters={"site": self.name, "status": "Active"},
			pluck="name",
		)

		for subscription in app_subscriptions:
			subscription_doc = frappe.get_doc("Marketplace App Subscription", subscription)
			subscription_doc.disable()

		subscriptions = frappe.get_all("Subscription", {"site": self.name, "enabled": 1}, pluck="name")
		for subscription in subscriptions:
			subscription_doc = frappe.get_doc("Subscription", subscription)
			subscription_doc.disable()

	def can_change_plan(self, ignore_card_setup):
		if is_system_user(frappe.session.user):
			return

		if ignore_card_setup:
			# ignore card setup for prepaid app payments
			return

		if bool(frappe.db.get_value("Cluster", self.cluster, "hybrid")):
			# skip validation if site is on hybrid server
			return

		team = frappe.get_doc("Team", self.team)

		if team.parent_team:
			team = frappe.get_doc("Team", team.parent_team)

		if team.payment_mode == "Paid By Partner" and team.billing_team:
			team = frappe.get_doc("Team", team.billing_team)

		if team.is_defaulter():
			frappe.throw("Cannot change plan because you have unpaid invoices", CannotChangePlan)

		if not (team.default_payment_method or team.get_balance()):
			frappe.throw(
				"Cannot change plan because you haven't added a card and not have enough balance",
				CannotChangePlan,
			)

	# TODO: rename to change_plan and remove the need for ignore_card_setup param
	@dashboard_whitelist()
	def set_plan(self, plan):
		from press.api.site import validate_plan

		validate_plan(self.server, plan)
		self.change_plan(plan)

	def change_plan(self, plan, ignore_card_setup=False):
		self.can_change_plan(ignore_card_setup)
		plan_config = self.get_plan_config(plan)

		if (
			frappe.db.exists(
				"Subscription",
				{"enabled": 1, "site": self.name, "document_type": "Marketplace App"},
			)
			and self.trial_end_date
		):
			plan_config["app_include_js"] = []

		self._update_configuration(plan_config)
		ret = frappe.get_doc(
			{
				"doctype": "Site Plan Change",
				"site": self.name,
				"from_plan": self.plan,
				"to_plan": plan,
			}
		).insert()

		self.reload()
		if self.status == "Suspended":
			self.unsuspend_if_applicable()
		else:
			# trigger agent job only once
			self.update_site_config(plan_config)

		if self.trial_end_date:
			self.reload()
			self.trial_end_date = ""
			self.save()

		frappe.enqueue_doc(
			self.doctype,
			self.name,
			"revoke_database_access_on_plan_change",
			enqueue_after_commit=True,
		)
		return ret

	def archive_site_database_users(self):
		db_users = frappe.get_all(
			"Site Database User",
			filters={
				"site": self.name,
				"status": ("!=", "Archived"),
			},
			pluck="name",
		)

		for db_user in db_users:
			frappe.get_doc("Site Database User", db_user).archive(
				raise_error=False, skip_remove_db_user_step=True
			)

	def revoke_database_access_on_plan_change(self):
		# If the new plan doesn't have database access, disable it
		if frappe.db.get_value("Site Plan", self.plan, "database_access"):
			return

		self.archive_site_database_users()

	def unsuspend_if_applicable(self):
		try:
			usage = frappe.get_last_doc("Site Usage", {"site": self.name})
		except frappe.DoesNotExistError:
			# If no doc is found, it means the site was created a few moments before
			# team was suspended, potentially due to failure in payment. Don't unsuspend
			# site in that case. team.unsuspend_sites should handle that, then.
			return

		plan_name = self.plan
		# get plan from subscription
		if not plan_name:
			subscription = self.subscription
			if not subscription:
				return
			plan_name = subscription.plan

		plan = frappe.get_doc("Site Plan", plan_name)

		disk_usage = usage.public + usage.private
		if usage.database < plan.max_database_usage and disk_usage < plan.max_storage_usage:
			self.current_database_usage = (usage.database / plan.max_database_usage) * 100
			self.current_disk_usage = ((usage.public + usage.private) / plan.max_storage_usage) * 100
			self.unsuspend(reason="Plan Upgraded")

	@dashboard_whitelist()
	@site_action(["Active", "Broken"])
	def deactivate(self):
		plan = frappe.db.get_value("Site Plan", self.plan, ["is_frappe_plan", "is_trial_plan"], as_dict=True)
		if self.plan and plan.is_trial_plan:
			frappe.throw(_("Cannot deactivate site on a trial plan"))

		if self.plan and plan.is_frappe_plan:
			frappe.throw(_("Cannot deactivate site on a Frappe plan"))

		log_site_activity(self.name, "Deactivate Site")
		self.status = "Inactive"
		self.update_site_config({"maintenance_mode": 1})
		self.update_site_status_on_proxy("deactivated")

	@dashboard_whitelist()
	@site_action(["Inactive", "Broken"])
	def activate(self):
		log_site_activity(self.name, "Activate Site")
		self.status = "Active"
		self.update_site_config({"maintenance_mode": 0})
		self.update_site_status_on_proxy("activated")
		self.reactivate_app_subscriptions()

	@frappe.whitelist()
	def suspend(self, reason=None, skip_reload=False):
		log_site_activity(self.name, "Suspend Site", reason)
		self.status = "Suspended"
		self.update_site_config({"maintenance_mode": 1})
		self.update_site_status_on_proxy("suspended", skip_reload=skip_reload)
		self.deactivate_app_subscriptions()

	def deactivate_app_subscriptions(self):
		frappe.db.set_value(
			"Marketplace App Subscription",
			{"status": "Active", "site": self.name},
			{"status": "Inactive"},
		)

	def reactivate_app_subscriptions(self):
		frappe.db.set_value(
			"Marketplace App Subscription",
			{"status": "Inactive", "site": self.name},
			{"status": "Active"},
		)

	@frappe.whitelist()
	@site_action(["Suspended"])
	def unsuspend(self, reason=None):
		log_site_activity(self.name, "Unsuspend Site", reason)
		self.status = "Active"
		self.update_site_config({"maintenance_mode": 0})
		self.update_site_status_on_proxy("activated")
		self.reactivate_app_subscriptions()

	@frappe.whitelist()
	def reset_site_usage(self):
		agent = Agent(self.server)
		agent.reset_site_usage(self)

	def update_site_status_on_proxy(self, status, skip_reload=False):
		proxy_server = frappe.db.get_value("Server", self.server, "proxy_server")
		agent = Agent(proxy_server, server_type="Proxy Server")
		agent.update_site_status(self.server, self.name, status, skip_reload)

	def get_user_details(self):
		if frappe.db.get_value("Team", self.team, "user") == "Administrator" and self.account_request:
			ar = frappe.get_doc("Account Request", self.account_request)
			user_email = ar.email
			user_first_name = ar.first_name
			user_last_name = ar.last_name
		else:
			user_email = frappe.db.get_value("Team", self.team, "user")
			user = frappe.db.get_value(
				"User", {"email": user_email}, ["first_name", "last_name"], as_dict=True
			)
			user_first_name = user.first_name if (user and user.first_name) else ""
			user_last_name = user.last_name if (user and user.last_name) else ""
		payload = {
			"email": user_email,
			"first_name": user_first_name or "",
			"last_name": user_last_name or "",
		}
		"""
		If the site is created for product trial,
		we might have collected the password from end-user for his site
		"""
		if self.account_request and self.standby_for_product and not self.is_standby:
			with contextlib.suppress(frappe.DoesNotExistError):
				# fetch the product trial request
				product_trial_request = frappe.get_doc(
					"Product Trial Request",
					{
						"account_request": self.account_request,
						"product_trial": self.standby_for_product,
						"site": self.name,
					},
				)
				setup_wizard_completion_mode = frappe.get_value(
					"Product Trial", product_trial_request.product_trial, "setup_wizard_completion_mode"
				)
				if setup_wizard_completion_mode == "manual":
					password = product_trial_request.get_user_login_password_from_signup_details()
					if password:
						payload["password"] = password

		return payload

	def setup_erpnext(self):
		account_request = frappe.get_doc("Account Request", self.account_request)
		agent = Agent(self.server)
		user = {
			"email": account_request.email,
			"first_name": account_request.first_name,
			"last_name": account_request.last_name,
		}
		config = {
			"setup_config": {
				"country": account_request.country,
				"timezone": account_request.timezone,
				"domain": account_request.domain,
				"currency": account_request.currency,
				"language": account_request.language,
				"company": account_request.company,
			}
		}
		agent.setup_erpnext(self, user, config)

	@property
	def subscription(self):
		name = frappe.db.get_value("Subscription", {"document_type": "Site", "document_name": self.name})
		return frappe.get_doc("Subscription", name) if name else None

	def can_charge_for_subscription(self, subscription=None):
		today = frappe.utils.getdate()
		return (
			self.status not in ["Archived", "Suspended"]
			and self.team
			and self.team != "Administrator"
			and not self.free
			and (today > get_datetime(self.trial_end_date).date() if self.trial_end_date else True)
		)

	def get_plan_name(self, plan=None):
		if not plan:
			plan = self.subscription_plan if hasattr(self, "subscription_plan") else self.plan
		if plan and not isinstance(plan, str):
			frappe.throw("Site.subscription_plan must be a string")
		return plan

	def get_plan_config(self, plan=None):
		plan = self.get_plan_name(plan)
		config = get_plan_config(plan)
		if plan in UNLIMITED_PLANS:
			# PERF: do not enable usage tracking on unlimited sites.
			config.pop("rate_limit", None)
		return config

	def set_latest_bench(self):
		from pypika.terms import PseudoColumn

		if not (self.domain and self.cluster and self.group):
			frappe.throw("domain, cluster and group are required to create site")

		proxy_servers_names = frappe.db.get_all(
			"Proxy Server Domain", {"domain": self.domain}, pluck="parent"
		)
		proxy_servers = frappe.db.get_all(
			"Proxy Server",
			{"status": "Active", "name": ("in", proxy_servers_names)},
			pluck="name",
		)

		"""
		For restricted plans, just choose any bench from the release groups and clusters combination
		For others, don't allow to deploy on those specific release group benches, choose anything except that
		"""

		release_group_names = []
		if self.get_plan_name():
			release_group_names = frappe.db.get_all(
				"Site Plan Release Group",
				pluck="release_group",
				filters={
					"parenttype": "Site Plan",
					"parentfield": "release_groups",
					"parent": self.get_plan_name(),
				},
			)

		Bench = frappe.qb.DocType("Bench")
		Server = frappe.qb.DocType("Server")

		bench_query = (
			frappe.qb.from_(Bench)
			.select(
				Bench.name,
				Bench.server,
				Bench.group,
				PseudoColumn(f"`tabBench`.`cluster` = '{self.cluster}' `in_primary_cluster`"),
			)
			.left_join(Server)
			.on(Bench.server == Server.name)
			.where(Server.proxy_server.isin(proxy_servers))
			.where(Bench.status == "Active")
			.orderby(PseudoColumn("in_primary_cluster"), order=frappe.qb.desc)
			.orderby(Server.use_for_new_sites, order=frappe.qb.desc)
			.orderby(Bench.creation, order=frappe.qb.desc)
			.limit(1)
		)
		if release_group_names:
			bench_query = bench_query.where(Bench.group.isin(release_group_names))
		else:
			restricted_release_group_names = frappe.db.get_all(
				"Site Plan Release Group",
				pluck="release_group",
				filters={"parenttype": "Site Plan", "parentfield": "release_groups"},
			)
			if self.group in restricted_release_group_names:
				frappe.throw(f"Site can't be deployed on this release group {self.group} due to restrictions")
			bench_query = bench_query.where(Bench.group == self.group)
		if self.server:
			bench_query = bench_query.where(Server.name == self.server)

		result = bench_query.run(as_dict=True)
		if len(result) == 0:
			frappe.throw("No bench available to deploy this site")
			return

		self.bench = result[0].name
		self.server = result[0].server
		if release_group_names:
			self.group = result[0].group

	def _create_initial_site_plan_change(self, plan):
		frappe.get_doc(
			{
				"doctype": "Site Plan Change",
				"site": self.name,
				"from_plan": "",
				"to_plan": plan,
				"type": "Initial Plan",
				"timestamp": self.creation,
			}
		).insert(ignore_permissions=True)

	def check_db_access_enabling(self):
		if frappe.db.get_value(
			"Agent Job",
			filters={
				"site": self.name,
				"job_type": "Add User to ProxySQL",
				"status": ["in", ["Running", "Pending"]],
			},
			for_update=True,
		):
			frappe.throw("Database Access is already being enabled on this site. Please check after a while.")

	def get_auto_update_info(self):
		fields = [
			"auto_updates_scheduled",
			"auto_update_last_triggered_on",
			"update_trigger_frequency",
			"update_trigger_time",
			"update_on_weekday",
			"update_end_of_month",
			"update_on_day_of_month",
		]
		return {field: self.get(field) for field in fields}

	def get_update_information(self):
		from press.press.doctype.site_update.site_update import (
			benches_with_available_update,
		)

		out = frappe._dict()
		out.update_available = self.bench in benches_with_available_update(site=self.name)
		if not out.update_available:
			return out

		bench: "Bench" = frappe.get_doc("Bench", self.bench)
		source = bench.candidate
		destinations = frappe.get_all(
			"Deploy Candidate Difference",
			filters={"source": source},
			limit=1,
			pluck="destination",
		)
		if not destinations:
			out.update_available = False
			return out

		destination = destinations[0]

		destination_candidate: "DeployCandidate" = frappe.get_doc("Deploy Candidate", destination)

		current_apps = bench.apps
		next_apps = destination_candidate.apps
		out.apps = get_updates_between_current_and_next_apps(current_apps, next_apps)

		out.installed_apps = self.apps
		out.update_available = any([app["update_available"] for app in out.apps])
		return out

	def fetch_running_optimize_tables_job(self):
		return frappe.db.exists(
			"Agent Job",
			{
				"site": self.name,
				"job_type": "Optimize Tables",
				"status": ["in", ["Undelivered", "Running", "Pending"]],
			},
		)

	@dashboard_whitelist()
	def optimize_tables(self, ignore_checks: bool = False):
		if not ignore_checks:
			# check for running `Optimize Tables` agent job
			if job := self.fetch_running_optimize_tables_job():
				return {
					"success": True,
					"message": "Optimize Tables job is already running on this site.",
					"job_name": job,
				}
			# check if `Optimize Tables` has run in last 1 hour
			recent_agent_job_name = frappe.db.exists(
				"Agent Job",
				{
					"site": self.name,
					"job_type": "Optimize Tables",
					"status": ["not in", ["Failure", "Delivery Failure"]],
					"creation": [">", frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1)],
				},
			)
			if recent_agent_job_name:
				return {
					"success": False,
					"message": "Optimize Tables job has already run in the last 1 hour. Try later.",
					"job_name": None,
				}

		agent = Agent(self.server)
		job_name = agent.optimize_tables(self).name
		return {
			"success": True,
			"message": "Optimize Tables has been triggered on this site.",
			"job_name": job_name,
		}

	@dashboard_whitelist()
	def get_database_performance_report(self):
		from press.press.report.mariadb_slow_queries.mariadb_slow_queries import get_data as get_slow_queries

		agent = Agent(self.server)
		# fetch slow queries of last 7 days
		slow_queries = get_slow_queries(
			frappe._dict(
				{
					"database": self.database_name,
					"start_datetime": frappe.utils.add_to_date(None, days=-7),
					"stop_datetime": frappe.utils.now_datetime(),
					"search_pattern": ".*",
					"max_lines": 2000,
					"normalize_queries": True,
				}
			)
		)
		# convert all the float to int
		for query in slow_queries:
			for key, value in query.items():
				if isinstance(value, float):
					query[key] = int(value)
		is_performance_schema_enabled = False
		if database_server := frappe.db.get_value("Server", self.server, "database_server"):
			is_performance_schema_enabled = frappe.db.get_value(
				"Database Server",
				database_server,
				"is_performance_schema_enabled",
			)
		result = None
		if is_performance_schema_enabled:
			with suppress(Exception):
				# for larger table or if database has any locks, fetching perf report will be failed
				result = agent.get_summarized_performance_report_of_database(self)
				# remove `parent` & `creation` indexes from unused_indexes
				result["unused_indexes"] = [
					index
					for index in result.get("unused_indexes", [])
					if index["index_name"] not in ["parent", "creation"]
				]

		if not result:
			result = {}
			result["unused_indexes"] = []
			result["redundant_indexes"] = []
			result["top_10_time_consuming_queries"] = []
			result["top_10_queries_with_full_table_scan"] = []

		# sort the slow queries by `rows_examined`
		result["slow_queries"] = sorted(slow_queries, key=lambda x: x["rows_examined"], reverse=True)
		result["is_performance_schema_enabled"] = is_performance_schema_enabled
		return result

	@property
	def server_logs(self):
		return Agent(self.server).get(f"benches/{self.bench}/sites/{self.name}/logs")

	def get_server_log(self, log):
		return Agent(self.server).get(f"benches/{self.bench}/sites/{self.name}/logs/{log}")

	def get_server_log_for_log_browser(self, log):
		return Agent(self.server).get(f"benches/{self.bench}/sites/{self.name}/logs_v2/{log}")

	@property
	def has_paid(self) -> bool:
		"""Has the site been paid for by customer."""
		invoice_items = frappe.get_all(
			"Invoice Item",
			{
				"document_type": self.doctype,
				"document_name": self.name,
				"Amount": (">", 0),
			},
			pluck="parent",
		)
		today = frappe.utils.getdate()
		today_last_month = frappe.utils.add_to_date(today, months=-1)
		last_month_last_date = frappe.utils.get_last_day(today_last_month)
		return frappe.db.exists(
			"Invoice",
			{
				"status": "Paid",
				"name": ("in", invoice_items or ["NULL"]),
				"period_end": (">=", last_month_last_date),
				# this month's or last month's invoice has been paid for
			},
		)

	@property
	def inbound_ip(self):
		server = frappe.db.get_value(
			"Server",
			self.server,
			["ip", "is_standalone", "proxy_server", "team"],
			as_dict=True,
		)
		if server.is_standalone:
			ip = server.ip
		else:
			ip = frappe.db.get_value("Proxy Server", server.proxy_server, "ip")
		return ip

	@property
	def current_usage(self):
		from press.api.analytics import get_current_cpu_usage

		result = frappe.db.get_all(
			"Site Usage",
			fields=["database", "public", "private"],
			filters={"site": self.name},
			order_by="creation desc",
			limit=1,
		)
		usage = result[0] if result else {}

		# number of hours until cpu usage resets
		now = frappe.utils.now_datetime()
		today_end = now.replace(hour=23, minute=59, second=59)
		hours_left_today = flt(time_diff_in_hours(today_end, now), 2)

		return {
			"cpu": flt(get_current_cpu_usage(self.name) / (3.6 * (10**9)), 5),
			"storage": usage.get("public", 0) + usage.get("private", 0),
			"database": usage.get("database", 0),
			"hours_until_cpu_usage_resets": hours_left_today,
		}

	@property
	def last_updated(self):
		result = frappe.db.get_all(
			"Site Activity",
			filters={"site": self.name, "action": "Update"},
			order_by="creation desc",
			limit=1,
			pluck="creation",
		)
		return result[0] if result else None

	@classmethod
	def get_sites_with_backup_time(cls) -> list[dict]:
		sites = frappe.qb.DocType(cls.DOCTYPE)
		return (
			frappe.qb.from_(sites)
			.select(sites.name, sites.backup_time)
			.where(sites.backup_time.isnotnull())
			.where(sites.status == "Active")
			.where(sites.skip_scheduled_backups == 0)
			.run(as_dict=True)
		)

	@classmethod
	def get_sites_for_backup(cls, interval: int):
		sites = cls.get_sites_without_backup_in_interval(interval)
		servers_with_backups = frappe.get_all(
			"Server",
			{"status": "Active", "skip_scheduled_backups": False},
			pluck="name",
		)
		return frappe.get_all(
			"Site",
			{
				"name": ("in", sites),
				"skip_scheduled_backups": False,
				"backup_time": ("is", "not set"),
				"server": ("in", servers_with_backups),
			},
			["name", "timezone", "server"],
			order_by="server",
			ignore_ifnull=True,
		)

	@classmethod
	def get_sites_without_backup_in_interval(cls, interval: int) -> list[str]:
		"""Return active sites that haven't had backup taken in interval hours."""
		interval_hrs_ago = frappe.utils.add_to_date(None, hours=-interval)
		all_sites = set(
			frappe.get_all(
				"Site",
				{
					"status": "Active",
					"creation": ("<=", interval_hrs_ago),
					"is_standby": False,
					"plan": ("not like", "%Trial"),
				},
				pluck="name",
			)
		)
		return list(
			all_sites
			- set(cls.get_sites_with_backup_in_interval(interval_hrs_ago))
			- set(cls.get_sites_with_pending_backups(interval_hrs_ago))
		)
		# TODO: query using creation time of account request for actual new sites <03-09-21, Balamurali M> #

	@classmethod
	def get_sites_with_pending_backups(cls, interval_hrs_ago: datetime) -> list[str]:
		return frappe.get_all(
			"Site Backup",
			{
				"status": ("in", ["Running", "Pending"]),
				"creation": (">=", interval_hrs_ago),
			},
			pluck="site",
		)

	@classmethod
	def get_sites_with_backup_in_interval(cls, interval_hrs_ago) -> list[str]:
		return frappe.get_all(
			"Site Backup",
			{
				"creation": (">", interval_hrs_ago),
				"status": ("!=", "Failure"),
				"owner": "Administrator",
			},
			pluck="site",
			ignore_ifnull=True,
		)

	@classmethod
	def exists(cls, subdomain, domain) -> bool:
		"""Check if subdomain is available"""
		banned_domains = frappe.get_all("Blocked Domain", {"block_for_all": 1}, pluck="name")
		if banned_domains and subdomain in banned_domains:
			return True
		return bool(
			frappe.db.exists("Blocked Domain", {"name": subdomain, "root_domain": domain})
			or frappe.db.exists(
				"Site",
				{
					"subdomain": subdomain,
					"domain": domain,
					"status": ("!=", "Archived"),
				},
			)
		)

	@frappe.whitelist()
	def run_after_migrate_steps(self):
		agent = Agent(self.server)
		agent.run_after_migrate_steps(self)

	@dashboard_whitelist()
	def reboot_instance(self):
		server = frappe.get_doc("Server", self.server)
		server.reboot_instance()

	@dashboard_whitelist()
	def stop_instance(self):
		server = frappe.get_doc("Server", self.server)
		server.stop_instance()

	@dashboard_whitelist()
	def start_instance(self):
		server = frappe.get_doc("Server", self.server)
		server.start_instance()

	@dashboard_whitelist()
	def disable_termination_protection(self):
		server = frappe.get_doc("Server", self.server)
		server.disable_termination_protection()

	@dashboard_whitelist()
	def enable_termination_protection(self):
		server = frappe.get_doc("Server", self.server)
		server.enable_termination_protection()

	@dashboard_whitelist()
	def drop_site(self):
		delete_site_and_related_docs(self)

	@frappe.whitelist()
	def get_actions(self):
		is_group_public = frappe.get_cached_value("Release Group", self.group, "public")
		server = frappe.get_doc("Server", self.server)
		server_state = server.instance_state
		termination_protection = server.termination_protection
		environment = server.environment

		actions = [
			{
				"action": "Start instance",
				"description": "Start the instance",
				"button_label": "Start",
				"condition": self.status != "Inactive" and server_state == "Stopped",
				"doc_method": "start_instance",
			},
			{
				"action": "Stop instance",
				"description": "Stop the instance",
				"button_label": "Stop",
				"condition": self.status != "Inactive" and server_state == "Running",
				"doc_method": "stop_instance",
			},
			{
				"action": "Reboot instance",
				"description": "Reboot the instance",
				"button_label": "Reboot",
				"condition": self.status != "Inactive" and server_state == "Running",
				"doc_method": "reboot_instance",
			},
			{
				"group": "Dangerous Actions",
				"action": "Disable termination protection",
				"description": "Termination protection prevents accidental deletion of your site. To delete your site, you must disable termination protection first",
				"button_label": "Disable",
				"doc_method": "disable_termination_protection",
				"condition": termination_protection == "Enabled" and environment != "Production",
			},
			{
				"group": "Dangerous Actions",
				"action": "Enable termination protection",
				"description": "Termination protection prevents accidental deletion of your site",
				"button_label": "Enable",
				"doc_method": "enable_termination_protection",
				"condition": termination_protection == "Disabled",
			},
			{
				"group": "Dangerous Actions",
				"action": "Drop site",
				"description": "When you drop your site, all site data is deleted forever",
				"button_label": "Drop",
				"doc_method": "drop_site",
				"condition": termination_protection == "Disabled" and environment != "Production",
			},
		]

		# These actions are not yet functional
		'''
		actions = [
			{
				"action": "Activate site",
				"description": "Activate site to make it accessible on the internet",
				"button_label": "Activate",
				"condition": self.status in ["Inactive", "Broken"],
				"doc_method": "activate",
			},
			{
				"action": "Manage database users",
				"description": "Manage users and permissions for your site database",
				"button_label": "Manage",
				"doc_method": "dummy",
				"condition": not self.hybrid_site,
			},
			{
				"action": "Schedule backup",
				"description": "Schedule a backup for this site",
				"button_label": "Schedule",
				"doc_method": "schedule_backup",
			},
			{
				"action": "Transfer site",
				"description": "Transfer ownership of this site to another team",
				"button_label": "Transfer",
				"doc_method": "send_change_team_request",
			},
			{
				"action": "Version upgrade",
				"description": "Upgrade your site to a major version",
				"button_label": "Upgrade",
				"doc_method": "upgrade",
				"condition": self.status == "Active",
			},
			{
				"action": "Change region",
				"description": "Move your site to a different region",
				"button_label": "Change",
				"doc_method": "change_region",
				"condition": self.status == "Active",
			},
			{
				"action": "Change bench group",
				"description": "Move your site to a different bench group",
				"button_label": "Change",
				"doc_method": "change_bench",
				"condition": self.status == "Active",
			},
			{
				"action": "Change server",
				"description": "Move your site to a different server",
				"button_label": "Change",
				"doc_method": "change_server",
				"condition": self.status == "Active" and not is_group_public,
			},
			{
				"action": "Clear cache",
				"description": "Clear cache on your site",
				"button_label": "Clear",
				"doc_method": "clear_site_cache",
			},
			{
				"action": "Deactivate site",
				"description": "Deactivated site is not accessible on the internet",
				"button_label": "Deactivate",
				"condition": self.status == "Active",
				"doc_method": "deactivate",
			},
			{
				"action": "Migrate site",
				"description": "Run bench migrate command on your site",
				"button_label": "Migrate",
				"doc_method": "migrate",
				"group": "Dangerous Actions",
			},
			{
				"action": "Restore with files",
				"description": "Restore with database, public and private files",
				"button_label": "Restore",
				"doc_method": "restore_site_from_files",
				"group": "Dangerous Actions",
			},
			{
				"action": "Restore from an existing site",
				"description": "Restore with database, public and private files from another site",
				"button_label": "Restore",
				"doc_method": "restore_site_from_files",
				"group": "Dangerous Actions",
			},
			{
				"action": "Reset site",
				"description": "Reset your site database to a clean state",
				"button_label": "Reset",
				"doc_method": "reinstall",
				"group": "Dangerous Actions",
			},
			{
				"action": "Drop site",
				"description": "When you drop your site, all site data is deleted forever",
				"button_label": "Drop",
				"doc_method": "archive",
				"group": "Dangerous Actions",
			},
		]
		'''

		return [d for d in actions if d.get("condition", True)]

	@property
	def hybrid_site(self) -> bool:
		return bool(frappe.get_cached_value("Server", self.server, "is_self_hosted"))

	@property
	def pending_for_long(self) -> bool:
		if self.status != "Pending":
			return False
		return (frappe.utils.now_datetime() - self.modified).total_seconds() > 60 * 60 * 4  # 4 hours

	@frappe.whitelist()
	def fetch_bench_from_agent(self):
		agent = Agent(self.server)
		benches_with_this_site = []
		for bench in agent.get("server")["benches"].values():
			if self.name in bench["sites"]:
				benches_with_this_site.append(bench["name"])
		if len(benches_with_this_site) == 1:
			frappe.db.set_value("Site", self.name, "bench", benches_with_this_site[0])

	@cached_property
	def is_on_dedicated_plan(self):
		return bool(frappe.db.get_value("Site Plan", self.plan, "dedicated_server_plan"))

	@frappe.whitelist()
	def forcefully_remove_site(self, bench):
		"""Bypass all agent/press callbacks and just remove this site from the target bench/server"""
		from press.utils import get_mariadb_root_password

		frappe.only_for("System Manager")

		if bench == self.bench:
			frappe.throw("Use <b>Archive Site</b> action to remove site from current bench")

		# Mimic archive_site method in the agent.py
		server = frappe.db.get_value("Bench", bench, ["server"])
		data = {
			"mariadb_root_password": get_mariadb_root_password(self),
			"force": True,
		}

		response = {"server": server, "bench": bench}
		agent = Agent(server)
		result = agent.request("POST", f"benches/{bench}/sites/{self.name}/archive", data, raises=False)
		if "job" in result:
			job = result["job"]
			response["job"] = job
		else:
			response["error"] = result["error"]
		self.add_comment(
			text=f"{frappe.session.user} attempted to forcefully remove site from {bench}.<br><pre>{json.dumps(response, indent=1)}</pre>"
		)
		return response

	@dashboard_whitelist()
	def fetch_database_table_schema(self, reload=False):
		"""
		Store dump in redis cache
		"""
		key_for_schema = f"database_table_schema__data:{self.name}"
		key_for_schema_status = (
			f"database_table_schema__status:{self.name}"  # 1 - loading, 2 - done, None - not available
		)

		if reload:
			frappe.cache().delete_value(key_for_schema)
			frappe.cache().delete_value(key_for_schema_status)

		status = frappe.utils.cint(frappe.cache().get_value(key_for_schema_status))
		if status:
			if status == 1:
				return {
					"loading": True,
					"data": [],
				}
			if status == 2:
				return {
					"loading": False,
					"data": json.loads(frappe.cache().get_value(key_for_schema)),
				}

		# Check if any agent job is created within 5 minutes and in pending/running condition
		# Checks to prevent duplicate agent job creation due to race condition
		if not frappe.db.exists(
			"Agent Job",
			{
				"job_type": "Fetch Database Table Schema",
				"site": self.name,
				"status": ["in", ["Undelivered", "Pending", "Running"]],
				"creation": (">", frappe.utils.add_to_date(None, minutes=-5)),
			},
		):
			# create the agent job and put it in loading state
			frappe.cache().set_value(key_for_schema_status, 1, expires_in_sec=600)
			Agent(self.server).fetch_database_table_schema(
				self, include_index_info=True, include_table_size=True
			)
		return {
			"loading": True,
			"data": [],
		}

	@dashboard_whitelist()
	def fetch_database_processes(self):
		agent = Agent(self.server)
		if agent.should_skip_requests():
			return None
		return agent.fetch_database_processes(self)

	@dashboard_whitelist()
	def kill_database_process(self, id):
		agent = Agent(self.server)
		if agent.should_skip_requests():
			return None
		return agent.kill_database_process(self, id)

	@dashboard_whitelist()
	def run_sql_query_in_database(self, query: str, commit: bool):
		if not query:
			return {"success": False, "output": "SQL Query cannot be empty"}
		doc = frappe.get_doc(
			{
				"doctype": "SQL Playground Log",
				"site": self.name,
				"team": self.team,
				"query": query,
				"committed": commit,
			}
		)
		response = Agent(self.server).run_sql_query_in_database(self, query, commit)
		doc.is_successful = response.get("success", False)
		doc.insert(ignore_permissions=True)
		return response

	@dashboard_whitelist()
	def suggest_database_indexes(self):
		from press.press.report.mariadb_slow_queries.mariadb_slow_queries import get_data as get_slow_queries

		existing_agent_job_name = frappe.db.exists(
			"Agent Job",
			{
				"site": self.name,
				"status": ("not in", ("Failure", "Delivery Failure")),
				"job_type": "Analyze Slow Queries",
				"creation": (
					">",
					frappe.utils.add_to_date(None, minutes=-30),
				),
				"retry_count": 0,
			},
		)

		if existing_agent_job_name:
			existing_agent_job = frappe.get_doc("Agent Job", existing_agent_job_name)
			if existing_agent_job.status == "Success":
				return {
					"loading": False,
					"data": json.loads(existing_agent_job.data).get("result", []),
				}
			return {
				"loading": True,
				"data": [],
			}

		# fetch slow queries of last 7 days
		slow_queries = get_slow_queries(
			frappe._dict(
				{
					"database": self.database_name,
					"start_datetime": frappe.utils.add_to_date(None, days=-7),
					"stop_datetime": frappe.utils.now_datetime(),
					"search_pattern": ".*",
					"max_lines": 1000,
					"normalize_queries": True,
				}
			)
		)
		slow_queries = [{"example": x["example"], "normalized": x["query"]} for x in slow_queries]
		if len(slow_queries) == 0:
			return {
				"loading": False,
				"data": [],
			}
		agent = Agent(self.server)
		agent.analyze_slow_queries(self, slow_queries)

		return {
			"loading": True,
			"data": [],
		}

	@dashboard_whitelist()
	def add_database_index(self, table, column):
		record = frappe.db.exists(
			"Agent Job",
			{
				"site": self.name,
				"status": ["in", ["Undelivered", "Running", "Pending"]],
				"job_type": "Add Database Index",
			},
		)
		if record:
			return {
				"success": False,
				"message": "There is already a job running for adding database index. Please wait until finished.",
				"job_name": record,
			}
		doctype = get_doctype_name(table)
		agent = Agent(self.server)
		job = agent.add_database_index(self, doctype=doctype, columns=[column])
		return {
			"success": True,
			"message": "Database index will be added on site.",
			"job_name": job.name,
		}
	
	@frappe.whitelist()
	def install_site(self):
		frappe.enqueue(self._install_site, queue="long", job_name=f"install_site_{self.name}", timeout=3600)
		self.status = "Installing"
		self.save()

	def _install_site(self):
		site = SiteSetup(self)
		site.execute()


def site_cleanup_after_archive(site):
	delete_site_domains(site)
	delete_site_subdomain(site)
	release_name(site)


def delete_site_subdomain(site):
	site_doc = frappe.get_doc("Site", site)
	domain = frappe.get_doc("Root Domain", site_doc.domain)
	is_standalone = frappe.get_value("Server", site_doc.server, "is_standalone")
	if is_standalone:
		proxy_server = site_doc.server
	else:
		proxy_server = frappe.get_value("Server", site_doc.server, "proxy_server")
	site_doc.remove_dns_record(domain, proxy_server, site)


def delete_site_domains(site):
	domains = frappe.get_all("Site Domain", {"site": site})
	frappe.db.set_value("Site", site, "host_name", None)
	for domain in domains:
		frappe.delete_doc("Site Domain", domain.name)


def release_name(name):
	if ".archived" in name:
		return
	new_name = f"{name}.archived"
	new_name = append_number_if_name_exists("Site", new_name, separator=".")
	frappe.rename_doc("Site", name, new_name)


def process_fetch_database_table_schema_job_update(job):
	key_for_schema = f"database_table_schema__data:{job.site}"
	key_for_schema_status = (
		f"database_table_schema__status:{job.site}"  # 1 - loading, 2 - done, None - not available
	)

	if job.status in ["Failure", "Delivery Failure"]:
		frappe.cache().delete_value(key_for_schema)
		frappe.cache().delete_value(key_for_schema_status)
		return

	if job.status == "Success":
		"""
		Support old agent versions
		Remove this once all agents are updated
		"""
		data = json.loads(job.data)
		is_old_agent = False

		if len(data) > 0 and isinstance(data[next(iter(data.keys()))], list):
			is_old_agent = True

		if is_old_agent:
			data_copy = data.copy()
			data = {}
			for key, value in data_copy.items():
				data[key] = {
					"columns": value,
					"size": {
						"data_length": 0,
						"index_length": 0,
						"total_size": 0,
					},  # old agent api doesn't have size info
				}
				for column in data[key]["columns"]:
					column["index_info"] = {
						"index_usage": {x: 0 for x in column["indexes"]},  # just fill some dummy value
						"indexes": column["indexes"],
						"is_indexed": len(column["indexes"]) > 0,
					}

		frappe.cache().set_value(key_for_schema, json.dumps(data), expires_in_sec=6000)
		frappe.cache().set_value(key_for_schema_status, 2, expires_in_sec=6000)


def process_new_site_job_update(job):  # noqa: C901
	site_status = frappe.get_value("Site", job.site, "status", for_update=True)

	other_job_types = {
		"Add Site to Upstream": ("New Site", "New Site from Backup"),
		"New Site": ("Add Site to Upstream",),
		"New Site from Backup": ("Add Site to Upstream",),
	}[job.job_type]

	first = job.status
	second = frappe.get_value(
		"Agent Job",
		{"job_type": ("in", other_job_types), "site": job.site},
		"status",
		for_update=True,
	)

	backup_tests = frappe.get_all(
		"Backup Restoration Test",
		dict(test_site=job.site, status="Running"),
		pluck="name",
	)

	if "Success" == first == second:
		updated_status = "Active"
		marketplace_app_hook(site=Site("Site", job.site), op="install")
	elif "Failure" in (first, second) or "Delivery Failure" in (first, second):
		updated_status = "Broken"
	elif "Running" in (first, second):
		updated_status = "Installing"
	else:
		updated_status = "Pending"

	status_map = {
		"Active": "Success",
		"Broken": "Failure",
		"Installing": "Running",
		"Pending": "Running",
	}

	if updated_status != site_status:
		if backup_tests:
			frappe.db.set_value(
				"Backup Restoration Test",
				backup_tests[0],
				"status",
				status_map[updated_status],
			)
			frappe.db.commit()

		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)

	if job.status == "Success":
		request_data = json.loads(job.request_data)
		if "create_user" in request_data:
			frappe.db.set_value("Site", job.site, "additional_system_user_created", True)
			frappe.db.commit()

	# Update in product trial request
	if job.job_type in ("New Site", "Add Site to Upstream") and updated_status in (
		"Active",
		"Broken",
	):
		update_product_trial_request_status_based_on_site_status(job.site, updated_status == "Active")

	# check if new bench related to a site group deploy
	site_group_deploy = frappe.db.get_value(
		"Site Group Deploy",
		{
			"site": job.site,
			"status": "Creating Site",
		},
	)
	if site_group_deploy:
		frappe.get_doc("Site Group Deploy", site_group_deploy).update_site_group_deploy_on_process_job(job)


def update_product_trial_request_status_based_on_site_status(site, is_site_active):
	records = frappe.get_list("Product Trial Request", filters={"site": site}, fields=["name"])
	if not records:
		return
	product_trial_request = frappe.get_doc("Product Trial Request", records[0].name, for_update=True)
	if is_site_active:
		mode = frappe.get_value(
			"Product Trial", product_trial_request.product_trial, "setup_wizard_completion_mode"
		)
		if mode != "auto":
			product_trial_request.status = "Site Created"
			product_trial_request.site_creation_completed_on = now_datetime()
			product_trial_request.save(ignore_permissions=True)
		else:
			product_trial_request.complete_setup_wizard()
	else:
		product_trial_request.status = "Error"
		product_trial_request.save(ignore_permissions=True)


def process_complete_setup_wizard_job_update(job):
	records = frappe.get_list("Product Trial Request", filters={"site": job.site}, fields=["name"])
	if not records:
		return
	product_trial_request = frappe.get_doc("Product Trial Request", records[0].name, for_update=True)
	if job.status == "Success":
		frappe.db.set_value("Site", job.site, "additional_system_user_created", True)
		product_trial_request.status = "Site Created"
		product_trial_request.site_creation_completed_on = now_datetime()
		product_trial_request.save(ignore_permissions=True)
	elif job.status in ("Failure", "Delivery Failure"):
		product_trial_request.status = "Error"
		product_trial_request.save(ignore_permissions=True)


def get_remove_step_status(job):
	remove_step_name = {
		"Archive Site": "Archive Site",
		"Remove Site from Upstream": "Remove Site File from Upstream Directory",
	}[job.job_type]

	return frappe.db.get_value(
		"Agent Job Step",
		{"step_name": remove_step_name, "agent_job": job.name},
		"status",
		for_update=True,
	)


def process_archive_site_job_update(job):
	site_status = frappe.get_value("Site", job.site, "status", for_update=True)

	other_job_type = {
		"Remove Site from Upstream": "Archive Site",
		"Archive Site": "Remove Site from Upstream",
	}[job.job_type]

	try:
		other_job = frappe.get_last_doc(
			"Agent Job",
			filters={"job_type": other_job_type, "site": job.site},
			for_update=True,
		)
	except frappe.DoesNotExistError:
		# Site is already renamed, the other job beat us to it
		# Our work is done
		return

	first = get_remove_step_status(job)
	second = get_remove_step_status(other_job)

	if (
		("Success" == first == second)
		or ("Skipped" == first == second)
		or sorted(("Success", "Skipped")) == sorted((first, second))
	):
		updated_status = "Archived"
	elif "Failure" in (first, second):
		updated_status = "Broken"
	elif "Delivery Failure" == first == second:
		updated_status = "Active"
	elif "Delivery Failure" in (first, second):
		updated_status = "Broken"
	else:
		updated_status = "Pending"

	if updated_status != site_status:
		frappe.db.set_value(
			"Site",
			job.site,
			{"status": updated_status, "archive_failed": updated_status != "Archived"},
		)
		if updated_status == "Archived":
			site_cleanup_after_archive(job.site)


def process_install_app_site_job_update(job):
	updated_status = {
		"Pending": "Pending",
		"Running": "Installing",
		"Success": "Active",
		"Failure": "Active",
		"Delivery Failure": "Active",
	}[job.status]

	site_status = frappe.get_value("Site", job.site, "status")
	if updated_status != site_status:
		if job.status == "Success":
			site = frappe.get_doc("Site", job.site)
			app = json.loads(job.request_data).get("name")
			app_doc = find(site.apps, lambda x: x.app == app)
			if not app_doc:
				site.append("apps", {"app": app})
				site.save()
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)


def process_uninstall_app_site_job_update(job):
	updated_status = {
		"Pending": "Pending",
		"Running": "Installing",
		"Success": "Active",
		"Failure": "Active",
		"Delivery Failure": "Active",
	}[job.status]

	site_status = frappe.get_value("Site", job.site, "status")
	if updated_status != site_status:
		if job.status == "Success":
			site = frappe.get_doc("Site", job.site)
			app = job.request_path.rsplit("/", 1)[-1]
			app_doc = find(site.apps, lambda x: x.app == app)
			if app_doc:
				site.remove(app_doc)
				site.save()
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)


def process_marketplace_hooks_for_backup_restore(apps_from_backup: set[str], site: Site):
	site_apps = set([app.app for app in site.apps])
	apps_to_install = apps_from_backup - site_apps
	apps_to_uninstall = site_apps - apps_from_backup
	for app in apps_to_install:
		if (
			frappe.get_cached_value("Marketplace App", app, "subscription_type") == "Free"
		):  # like india_compliance; no need to check subscription
			marketplace_app_hook(app=app, site=site, op="install")
	for app in apps_to_uninstall:
		if (
			frappe.get_cached_value("Marketplace App", app, "subscription_type") == "Free"
		):  # like india_compliance; no need to check subscription
			marketplace_app_hook(app=app, site=site, op="uninstall")


def process_restore_job_update(job, force=False):
	"""
	force: force updates apps table sync
	"""
	updated_status = {
		"Pending": "Pending",
		"Running": "Installing",
		"Success": "Active",
		"Failure": "Broken",
		"Delivery Failure": "Active",
	}[job.status]

	site_status = frappe.get_value("Site", job.site, "status")
	if force or updated_status != site_status:
		if job.status == "Success":
			apps_from_backup: list[str] = [line.split()[0] for line in job.output.splitlines() if line]
			site = Site("Site", job.site)
			process_marketplace_hooks_for_backup_restore(set(apps_from_backup), site)
			site.set_apps(apps_from_backup)
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)


def process_reinstall_site_job_update(job):
	updated_status = {
		"Pending": "Pending",
		"Running": "Installing",
		"Success": "Active",
		"Failure": "Broken",
		"Delivery Failure": "Active",
	}[job.status]

	site_status = frappe.get_value("Site", job.site, "status")
	if updated_status != site_status:
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)
	if job.status == "Success":
		frappe.db.set_value("Site", job.site, "setup_wizard_complete", 0)


def process_migrate_site_job_update(job):
	updated_status = {
		"Pending": "Pending",
		"Running": "Updating",
		"Success": "Active",
		"Failure": "Broken",
		"Delivery Failure": "Active",
	}[job.status]

	if updated_status == "Active":
		site: Site = frappe.get_doc("Site", job.site)
		if site.status_before_update:
			site.reset_previous_status(fix_broken=True)
			return
	site_status = frappe.get_value("Site", job.site, "status")
	if updated_status != site_status:
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)


def get_rename_step_status(job):
	rename_step_name = {
		"Rename Site": "Rename Site",
		"Rename Site on Upstream": "Rename Site File in Upstream Directory",
	}[job.job_type]

	return frappe.db.get_value(
		"Agent Job Step",
		{"step_name": rename_step_name, "agent_job": job.name},
		"status",
		for_update=True,
	)


def process_rename_site_job_update(job):  # noqa: C901
	site_status = frappe.get_value("Site", job.site, "status", for_update=True)

	other_job_type = {
		"Rename Site": "Rename Site on Upstream",
		"Rename Site on Upstream": "Rename Site",
	}[job.job_type]

	if job.job_type == "Rename Site" and job.status == "Success":
		request_data = json.loads(job.request_data)
		if "create_user" in request_data:
			frappe.db.set_value("Site", job.site, "additional_system_user_created", True)

	try:
		other_job = frappe.get_last_doc(
			"Agent Job",
			filters={"job_type": other_job_type, "site": job.site},
			for_update=True,
		)
	except frappe.DoesNotExistError:
		# Site is already renamed, he other job beat us to it
		# Our work is done
		return

	first = get_rename_step_status(job)
	second = get_rename_step_status(other_job)

	if "Success" == first == second:
		update_records_for_rename(job)
		# update job obj with new name
		job.reload()
		updated_status = "Active"
		from press.press.doctype.site.pool import create as create_pooled_sites

		create_pooled_sites()

	elif "Failure" in (first, second):
		updated_status = "Broken"
	elif "Delivery Failure" == first == second:
		updated_status = "Active"
	elif "Delivery Failure" in (first, second):
		updated_status = "Broken"
	elif "Running" in (first, second):
		updated_status = "Updating"
	else:
		updated_status = "Pending"

	if updated_status != site_status:
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)


def process_move_site_to_bench_job_update(job):
	updated_status = {
		"Pending": "Pending",
		"Running": "Updating",
		"Failure": "Broken",
	}.get(job.status)
	if job.status in ("Success", "Failure"):
		dest_bench = json.loads(job.request_data).get("target")
		dest_group = frappe.db.get_value("Bench", dest_bench, "group")

		move_site_step_status = frappe.db.get_value(
			"Agent Job Step",
			{"step_name": "Move Site", "agent_job": job.name},
			"status",
		)
		if move_site_step_status == "Success":
			frappe.db.set_value("Site", job.site, "bench", dest_bench)
			frappe.db.set_value("Site", job.site, "group", dest_group)
	if updated_status:
		frappe.db.set_value("Site", job.site, "status", updated_status)
		create_site_status_update_webhook_event(job.site)
		return
	if job.status == "Success":
		site = frappe.get_doc("Site", job.site)
		site.reset_previous_status(fix_broken=True)


def update_records_for_rename(job):
	"""Update press records for successful site rename."""
	data = json.loads(job.request_data)
	new_name = data["new_name"]
	if new_name == job.site:  # idempotency
		return

	site = frappe.get_doc("Site", job.site, for_update=True)
	if site.host_name == job.site:
		# Host name already updated in f server, no need to create another job
		site._update_configuration({"host_name": f"https://{new_name}"})
		site.db_set("host_name", new_name)

	frappe.rename_doc("Site", job.site, new_name)
	frappe.rename_doc("Site Domain", job.site, new_name)


def process_restore_tables_job_update(job):
	updated_status = {
		"Pending": "Pending",
		"Running": "Updating",
		"Success": "Active",
		"Failure": "Broken",
	}[job.status]

	site_status = frappe.get_value("Site", job.site, "status")
	if updated_status != site_status:
		if updated_status == "Active":
			frappe.get_doc("Site", job.site).reset_previous_status(fix_broken=True)
		else:
			frappe.db.set_value("Site", job.site, "status", updated_status)
			create_site_status_update_webhook_event(job.site)


def process_create_user_job_update(job):
	if job.status == "Success":
		frappe.db.set_value("Site", job.site, "additional_system_user_created", True)
		update_product_trial_request_status_based_on_site_status(job.site, True)
	elif job.status in ("Failure", "Delivery Failure"):
		update_product_trial_request_status_based_on_site_status(job.site, False)


get_permission_query_conditions = get_permission_query_conditions_for_doctype("Site")


def prepare_site(site: str, subdomain: str | None = None) -> dict:
	# prepare site details
	doc = frappe.get_doc("Site", site)
	site_name = subdomain if subdomain else "brt-" + doc.subdomain
	app_plans = [app.app for app in doc.apps]
	backups = frappe.get_all(
		"Site Backup",
		dict(status="Success", site=site, files_availability="Available", offsite=1),
		pluck="name",
	)
	if not backups:
		frappe.throw("Backup Files not found.")
	backup = frappe.get_doc("Site Backup", backups[0])

	files = {
		"config": backup.remote_config_file,
		"database": backup.remote_database_file,
		"public": backup.remote_public_file,
		"private": backup.remote_private_file,
	}
	return {
		"domain": frappe.db.get_single_value("Press Settings", "domain"),
		"plan": doc.plan,
		"name": site_name,
		"group": doc.group,
		"selected_app_plans": {},
		"apps": app_plans,
		"files": files,
	}


@frappe.whitelist()
def options_for_new(group: str | None = None, selected_values=None) -> dict:
	domain = frappe.db.get_single_value("Press Settings", "domain")
	selected_values = frappe.parse_json(selected_values) if selected_values else frappe._dict()

	versions = []
	bench = None
	apps = []
	clusters = []

	versions_filters = {"public": True}
	if not group:
		versions_filters.update({"status": ("!=", "End of Life")})

	versions = frappe.db.get_all(
		"Frappe Version",
		["name", "default", "status", "number"],
		versions_filters,
		order_by="number desc",
	)
	for v in versions:
		v.label = v.name
		v.value = v.name

	if selected_values.version:
		bench = _get_bench_for_new(selected_values.version)
		apps = _get_apps_of_bench(selected_values.version, bench) if bench else []
		cluster_names = unique(
			frappe.db.get_all(
				"Bench",
				filters={"candidate": frappe.db.get_value("Bench", bench, "candidate")},
				pluck="cluster",
			)
		)
		clusters = frappe.db.get_all(
			"Cluster",
			filters={"name": ("in", cluster_names), "public": True},
			fields=["name", "title", "image", "beta"],
		)
		for cluster in clusters:
			cluster.label = cluster.title
			cluster.value = cluster.name

	return {
		"domain": domain,
		"bench": bench,
		"versions": versions,
		"apps": apps,
		"clusters": clusters,
	}


def _get_bench_for_new(version):
	restricted_release_group_names = frappe.db.get_all(
		"Site Plan Release Group",
		pluck="release_group",
		filters={"parenttype": "Site Plan", "parentfield": "release_groups"},
	)
	release_group = frappe.db.get_value(
		"Release Group",
		fieldname=["name", "`default`", "title"],
		filters={
			"enabled": 1,
			"public": 1,
			"version": version,
			"name": ("not in", restricted_release_group_names),
		},
		order_by="creation desc",
		as_dict=1,
	)
	if not release_group:
		return None

	return frappe.db.get_value(
		"Bench",
		filters={"status": "Active", "group": release_group.name},
		order_by="creation desc",
	)


def _get_apps_of_bench(version, bench):
	team = frappe.local.team().name
	bench_apps = frappe.db.get_all("Bench App", {"parent": bench}, pluck="source")
	app_sources = frappe.get_all(
		"App Source",
		[
			"name",
			"app",
			"repository_url",
			"repository",
			"repository_owner",
			"branch",
			"team",
			"public",
			"app_title",
			"frappe",
		],
		filters={"name": ("in", bench_apps), "frappe": 0},
		or_filters={"public": True, "team": team},
	)
	for app in app_sources:
		app.label = app.app_title
		app.value = app.app
	apps = sorted(app_sources, key=lambda x: bench_apps.index(x.name))
	marketplace_apps = frappe.db.get_all(
		"Marketplace App",
		fields=["title", "image", "description", "app", "route"],
		filters={"app": ("in", [app.app for app in apps])},
	)
	for app in apps:
		marketplace_details = find(marketplace_apps, lambda x: x.app == app.app)
		if marketplace_details:
			app.update(marketplace_details)
			app.plans = get_plans_for_app(app.app, version)
	return apps


def sync_sites_setup_wizard_complete_status():
	team_name = frappe.get_value("Team", {"user": "Administrator"}, "name")
	sites = frappe.get_all(
		"Site",
		filters={
			"status": "Active",
			"setup_wizard_complete": 0,
			"setup_wizard_status_check_retries": ("<", 18),
			"setup_wizard_status_check_next_retry_on": ("<=", frappe.utils.now()),
			"team": ("!=", team_name),
		},
		pluck="name",
		order_by="RAND()",
		limit=100,
	)
	for site in sites:
		frappe.enqueue(
			"press.press.doctype.site.site.fetch_setup_wizard_complete_status_if_site_exists",
			site=site,
			queue="sync",
			job_id=f"fetch_setup_wizard_complete_status:{site}",
			deduplicate=True,
		)


def fetch_setup_wizard_complete_status_if_site_exists(site):
	if not frappe.db.exists("Site", site):
		return
	with suppress(frappe.DoesNotExistError):
		frappe.get_doc("Site", site).fetch_setup_wizard_complete_status()


def create_site_status_update_webhook_event(site: str):
	record = frappe.get_doc("Site", site)
	if record.team == "Administrator":
		return
	create_webhook_event("Site Status Update", record, record.team)


def delete_site_and_related_docs(doc):
	# Delete Site
	frappe.db.delete("Site Domain", doc.name)
	delete_linked_docs(doc)
	delete_dynamically_linked_docs(doc)
	doc.delete()

	# Delete Bench
	bench_doc = frappe.get_doc("Bench", doc.bench)
	delete_linked_docs(bench_doc)
	delete_dynamically_linked_docs(bench_doc)
	bench_doc.delete()
	
	# Delete Deploy
	deploy = frappe.db.get_value("Deploy Bench", {"bench": doc.bench}, "parent")
	frappe.delete_doc("Deploy", deploy)
	
	# Remove app server from Release Group
	release_group = frappe.get_doc("Release Group", bench_doc.group)
	servers = release_group.get("servers", [])
	servers = [server for server in servers if server.server != doc.server]
	release_group.set("servers", servers)
	release_group.save()
	
	# Delete App Server
	server_doc = frappe.get_doc("Server", doc.server)
	server_doc.terminate_instance()
	server_doc.reload()
	if server_doc.status == "Archived":
		delete_linked_docs(server_doc)
		delete_dynamically_linked_docs(server_doc)
		server_doc.delete()


def delete_linked_docs(doc, method="Delete"):
	link_fields = get_link_fields(doc.doctype)
	ignored_doctypes = set()

	if method == "Cancel" and (doc_ignore_flags := doc.get("ignore_linked_doctypes")):
		ignored_doctypes.update(doc_ignore_flags)
	if method == "Delete":
		ignored_doctypes.update(frappe.get_hooks("ignore_links_on_delete"))

	for lf in link_fields:
		link_dt, link_field, issingle = lf["parent"], lf["fieldname"], lf["issingle"]
		if link_dt in ignored_doctypes or (link_field == "amended_from" and method == "Cancel"):
			continue

		try:
			meta = frappe.get_meta(link_dt)
		except frappe.DoesNotExistError:
			frappe.clear_last_message()
			# This mostly happens when app do not remove their customizations, we shouldn't
			# prevent link checks from failing in those cases
			continue

		if issingle:
			if frappe.db.get_single_value(link_dt, link_field) == doc.name:
				raise_link_exists_exception(doc, link_dt, link_dt)
			continue

		fields = ["name", "docstatus"]

		if meta.istable:
			fields.extend(["parent", "parenttype"])

		for item in frappe.db.get_values(link_dt, {link_field: doc.name}, fields, as_dict=True):
			# available only in child table cases
			item_parent = getattr(item, "parent", None)
			linked_parent_doctype = item.parenttype if item_parent else link_dt

			if linked_parent_doctype in ignored_doctypes:
				continue

			if method != "Delete" and (method != "Cancel" or not DocStatus(item.docstatus).is_submitted()):
				# don't raise exception if not
				# linked to a non-cancelled doc when deleting or to a submitted doc when cancelling
				continue
			elif link_dt == doc.doctype and (item_parent or item.name) == doc.name:
				# don't raise exception if not
				# linked to same item or doc having same name as the item
				continue
			else:
				reference_docname = item_parent or item.name
				frappe.delete_doc(linked_parent_doctype, reference_docname, force=True, ignore_missing=True)


def delete_dynamically_linked_docs(doc, method="Delete"):
	for df in get_dynamic_link_map().get(doc.doctype, []):
		ignore_linked_doctypes = doc.get("ignore_linked_doctypes") or []

		if df.parent in frappe.get_hooks("ignore_links_on_delete") or (
			df.parent in ignore_linked_doctypes and method == "Cancel"
		):
			# don't check for communication and todo!
			continue

		meta = frappe.get_meta(df.parent)
		if meta.issingle:
			# dynamic link in single doc
			refdoc = frappe.db.get_singles_dict(df.parent)
			if (
				refdoc.get(df.options) == doc.doctype
				and refdoc.get(df.fieldname) == doc.name
				and (
					# linked to an non-cancelled doc when deleting
					(method == "Delete" and not DocStatus(refdoc.docstatus).is_cancelled())
					# linked to a submitted doc when cancelling
					or (method == "Cancel" and DocStatus(refdoc.docstatus).is_submitted())
				)
			):
				raise_link_exists_exception(doc, df.parent, df.parent)
		else:
			# dynamic link in table
			df["table"] = ", `parent`, `parenttype`, `idx`" if meta.istable else ""
			for refdoc in frappe.db.sql(
				"""select `name`, `docstatus` {table} from `tab{parent}` where
				`{options}`=%s and `{fieldname}`=%s""".format(**df),
				(doc.doctype, doc.name),
				as_dict=True,
			):
				# linked to an non-cancelled doc when deleting
				# or linked to a submitted doc when cancelling
				if (method == "Delete" and not DocStatus(refdoc.docstatus).is_cancelled()) or (
					method == "Cancel" and DocStatus(refdoc.docstatus).is_submitted()
				):
					reference_doctype = refdoc.parenttype if meta.istable else df.parent
					reference_docname = refdoc.parent if meta.istable else refdoc.name

					if reference_doctype in frappe.get_hooks("ignore_links_on_delete") or (
						reference_doctype in ignore_linked_doctypes and method == "Cancel"
					):
						# don't check for communication and todo!
						continue

					frappe.delete_doc(reference_doctype, reference_docname, force=True, ignore_missing=True)


def raise_link_exists_exception(doc, reference_doctype, reference_docname, row=""):
	doc_link = f'<a href="/app/Form/{doc.doctype}/{doc.name}">{doc.name}</a>'
	reference_link = f'<a href="/app/Form/{reference_doctype}/{reference_docname}">{reference_docname}</a>'

	# hack to display Single doctype only once in message
	if reference_doctype == reference_docname:
		reference_doctype = ""

	frappe.throw(
		_("Cannot delete or cancel because {0} {1} is linked with {2} {3} {4}").format(
			_(doc.doctype), doc_link, _(reference_doctype), reference_link, row
		),
		frappe.LinkExistsError,
	)
