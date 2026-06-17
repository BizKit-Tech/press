import frappe
from frappe.utils import add_to_date, today
from press.api.bizkit_site import force_delete


def _get_settings():
	grace_period = frappe.db.get_single_value("Press Settings", "temporary_site_grace_period_days") or 7
	warning_days = frappe.db.get_single_value("Press Settings", "temporary_site_warning_days") or 3
	return grace_period, warning_days


def _create_notification(team, site_name, title, message):
	notification_doc = frappe.get_doc({
		"doctype": "Press Notification",
		"team": team,
		"type": "Site Update",
		"document_type": "Site",
		"document_name": site_name,
		"class": "Info",
		"title": title,
		"message": message,
	})
	notification_doc.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.publish_realtime("press_notification", doctype="Press Notification", message={"team": team})


def _get_temporary_sites(extra_filters=""):
	"""Return sites with takedown_date set, on Development or Demo servers."""
	return frappe.db.sql("""
		SELECT s.name, s.team, s.server, s.status, s.takedown_date
		FROM `tabSite` s
		JOIN `tabServer` srv ON srv.name = s.server
		WHERE s.takedown_date IS NOT NULL
		  AND srv.environment IN ('Development', 'Demo')
		""" + extra_filters, as_dict=True)


def notify_upcoming_takedowns():
	grace_period, warning_days = _get_settings()
	warning_date = add_to_date(today(), days=warning_days)

	sites = _get_temporary_sites(f"""
		AND s.takedown_date = '{warning_date}'
		AND s.status NOT IN ('Inactive', 'Archived')
	""")

	for site in sites:
		try:
			archive_date = add_to_date(site.takedown_date, days=grace_period)
			_create_notification(
				site.team, site.name,
				"Site Scheduled for Suspension",
				f"Your site {site.name} is scheduled to be suspended on {site.takedown_date}. "
				f"It will be permanently deleted on {archive_date}."
			)
		except Exception:
			frappe.log_error("Temporary Site: notify_upcoming_takedowns failed", site.name)


def suspend_temporary_sites():
	grace_period, _ = _get_settings()

	sites = _get_temporary_sites(f"""
		AND s.takedown_date = '{today()}'
		AND s.status NOT IN ('Inactive', 'Archived')
	""")

	for site in sites:
		try:
			frappe.db.set_value("Site", site.name, "status", "Inactive")
			frappe.get_doc("Server", site.server).stop_instance()
			frappe.db.commit()
			archive_date = add_to_date(site.takedown_date, days=grace_period)
			_create_notification(
				site.team, site.name,
				"Site Suspended",
				f"Site {site.name} has been suspended and will be permanently deleted on {archive_date}."
			)
		except Exception:
			frappe.db.rollback()
			frappe.log_error("Temporary Site: suspend_temporary_sites failed", site.name)


def archive_expired_temporary_sites():
	grace_period, _ = _get_settings()

	sites = _get_temporary_sites(f"""
		AND s.status = 'Inactive'
		AND DATE_ADD(s.takedown_date, INTERVAL {int(grace_period)} DAY) <= '{today()}'
	""")

	for site in sites:
		try:
			site_doc = frappe.get_doc("Site", site.name)
			teardown_temporary_site(site_doc)
			_create_notification(
				site.team, site.name,
				"Site Permanently Deleted",
				f"Site {site.name} and its infrastructure have been permanently deleted."
			)
		except Exception:
			frappe.log_error("Temporary Site: archive_expired_temporary_sites failed", site.name)


def teardown_temporary_site(site_doc):
	cluster_name = site_doc.cluster
	server_name = site_doc.server
	bench_name = site_doc.bench
	release_group = site_doc.release_group

	# Get the DB server before we delete anything
	db_server_name = frappe.db.get_value("Server", server_name, "database_server")

	# 1. Delete site and linked docs
	force_delete("Site", site_doc.name)

	# 2. Delete bench and linked docs
	force_delete("Bench", bench_name)

	# 3. Delete release group server entry (not the whole RG — just remove this server)
	rg_doc = frappe.get_doc("Release Group", release_group)
	rg_doc.servers = [s for s in rg_doc.servers if s.server != server_name]
	rg_doc.save(ignore_permissions=True)
	frappe.db.commit()

	# 4. Terminate app server
	server_doc = frappe.get_doc("Server", server_name)
	server_doc.disable_termination_protection()
	server_doc.terminate_instance()
	force_delete("Server", server_name)

	# 5. If no other active servers in this cluster, tear down DB server + cluster
	remaining = frappe.db.count("Server", {"cluster": cluster_name, "status": ("!=", "Archived")})
	if remaining == 0 and db_server_name:
		db_doc = frappe.get_doc("Database Server", db_server_name)
		db_doc.disable_termination_protection()
		db_doc.terminate_instance()
		force_delete("Database Server", db_server_name)

		cluster_doc = frappe.get_doc("Cluster", cluster_name)
		cluster_doc.delete_vpc()
		force_delete("Cluster", cluster_name)
