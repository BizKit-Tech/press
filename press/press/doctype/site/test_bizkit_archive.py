import unittest
from unittest.mock import MagicMock, patch, call
from frappe.utils import add_to_date, today


class TestNotifyUpcomingTakedowns(unittest.TestCase):

	@patch("press.press.doctype.site.bizkit_archive._create_notification")
	@patch("press.press.doctype.site.bizkit_archive._get_temporary_sites")
	@patch("press.press.doctype.site.bizkit_archive._get_settings")
	def test_sends_notification_for_sites_due_for_warning(self, mock_settings, mock_get_sites, mock_notify):
		mock_settings.return_value = (7, 3)
		mock_get_sites.return_value = [
			{"name": "site1.example.com", "team": "team1", "server": "srv1",
			 "status": "Active", "takedown_date": add_to_date(today(), days=3)}
		]

		from press.press.doctype.site.bizkit_archive import notify_upcoming_takedowns
		notify_upcoming_takedowns()

		mock_notify.assert_called_once()
		args = mock_notify.call_args[0]
		assert args[1] == "site1.example.com"
		assert "suspended" in args[3].lower()

	@patch("press.press.doctype.site.bizkit_archive._create_notification")
	@patch("press.press.doctype.site.bizkit_archive._get_temporary_sites")
	@patch("press.press.doctype.site.bizkit_archive._get_settings")
	def test_skips_inactive_sites(self, mock_settings, mock_get_sites, mock_notify):
		mock_settings.return_value = (7, 3)
		mock_get_sites.return_value = []  # SQL filter already excludes Inactive

		from press.press.doctype.site.bizkit_archive import notify_upcoming_takedowns
		notify_upcoming_takedowns()

		mock_notify.assert_not_called()

	@patch("frappe.log_error")
	@patch("press.press.doctype.site.bizkit_archive._create_notification")
	@patch("press.press.doctype.site.bizkit_archive._get_temporary_sites")
	@patch("press.press.doctype.site.bizkit_archive._get_settings")
	def test_logs_error_and_continues_on_failure(self, mock_settings, mock_get_sites, mock_notify, mock_log_error):
		mock_settings.return_value = (7, 3)
		mock_get_sites.return_value = [
			{"name": "site1.example.com", "team": "team1", "server": "srv1",
			 "status": "Active", "takedown_date": add_to_date(today(), days=3)},
			{"name": "site2.example.com", "team": "team2", "server": "srv2",
			 "status": "Active", "takedown_date": add_to_date(today(), days=3)},
		]
		mock_notify.side_effect = [Exception("DB error"), None]

		from press.press.doctype.site.bizkit_archive import notify_upcoming_takedowns
		notify_upcoming_takedowns()

		mock_log_error.assert_called_once()
		assert mock_notify.call_count == 2  # attempted both sites


class TestSuspendTemporarySites(unittest.TestCase):

	@patch("press.press.doctype.site.bizkit_archive._create_notification")
	@patch("frappe.get_doc")
	@patch("frappe.db")
	@patch("press.press.doctype.site.bizkit_archive._get_temporary_sites")
	@patch("press.press.doctype.site.bizkit_archive._get_settings")
	def test_sets_status_inactive_and_stops_instance(self, mock_settings, mock_get_sites, mock_db, mock_get_doc, mock_notify):
		mock_settings.return_value = (7, 3)
		mock_get_sites.return_value = [
			{"name": "site1.example.com", "team": "team1", "server": "srv1",
			 "status": "Active", "takedown_date": today()}
		]
		mock_server = MagicMock()
		mock_get_doc.return_value = mock_server

		from press.press.doctype.site.bizkit_archive import suspend_temporary_sites
		suspend_temporary_sites()

		mock_db.set_value.assert_called_with("Site", "site1.example.com", "status", "Inactive")
		mock_server.stop_instance.assert_called_once()
		mock_notify.assert_called_once()


class TestArchiveExpiredTemporarySites(unittest.TestCase):

	@patch("press.press.doctype.site.bizkit_archive._create_notification")
	@patch("press.press.doctype.site.bizkit_archive.teardown_temporary_site")
	@patch("frappe.get_doc")
	@patch("press.press.doctype.site.bizkit_archive._get_temporary_sites")
	@patch("press.press.doctype.site.bizkit_archive._get_settings")
	def test_calls_teardown_for_expired_sites(self, mock_settings, mock_get_sites, mock_get_doc, mock_teardown, mock_notify):
		mock_settings.return_value = (7, 3)
		mock_get_sites.return_value = [
			{"name": "site1.example.com", "team": "team1", "server": "srv1",
			 "status": "Inactive", "takedown_date": add_to_date(today(), days=-8)}
		]
		mock_site_doc = MagicMock()
		mock_get_doc.return_value = mock_site_doc

		from press.press.doctype.site.bizkit_archive import archive_expired_temporary_sites
		archive_expired_temporary_sites()

		mock_teardown.assert_called_once_with(mock_site_doc)
		mock_notify.assert_called_once()


class TestTeardownTemporarySite(unittest.TestCase):

	@patch("press.press.doctype.site.bizkit_archive.force_delete")
	@patch("frappe.db")
	@patch("frappe.get_doc")
	def test_deletes_site_bench_server_and_cluster_when_last_server(self, mock_get_doc, mock_db, mock_force_delete):
		# Setup site_doc mock
		site_doc = MagicMock()
		site_doc.name = "site1.example.com"
		site_doc.cluster = "cluster1"
		site_doc.server = "srv1"
		site_doc.bench = "bench1"
		site_doc.release_group = "rg1"

		# db.get_value returns db_server, db.count returns 0 (last server)
		mock_db.get_value.return_value = "db-srv1"
		mock_db.count.return_value = 0

		mock_server = MagicMock()
		mock_db_server = MagicMock()
		mock_cluster = MagicMock()
		mock_rg = MagicMock()
		mock_rg.servers = []

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Server":
				return mock_server
			if doctype == "Database Server":
				return mock_db_server
			if doctype == "Cluster":
				return mock_cluster
			if doctype == "Release Group":
				return mock_rg
			return MagicMock()

		mock_get_doc.side_effect = get_doc_side_effect

		from press.press.doctype.site.bizkit_archive import teardown_temporary_site
		teardown_temporary_site(site_doc)

		# Site and bench deleted
		mock_force_delete.assert_any_call("Site", "site1.example.com")
		mock_force_delete.assert_any_call("Bench", "bench1")
		# Server terminated and deleted
		mock_server.terminate_instance.assert_called_once()
		mock_force_delete.assert_any_call("Server", "srv1")
		# DB server terminated and deleted (last server)
		mock_db_server.terminate_instance.assert_called_once()
		mock_force_delete.assert_any_call("Database Server", "db-srv1")
		# Cluster VPC deleted
		mock_cluster.delete_vpc.assert_called_once()
		mock_force_delete.assert_any_call("Cluster", "cluster1")

	@patch("press.press.doctype.site.bizkit_archive.force_delete")
	@patch("frappe.db")
	@patch("frappe.get_doc")
	def test_skips_cluster_teardown_when_other_servers_remain(self, mock_get_doc, mock_db, mock_force_delete):
		site_doc = MagicMock()
		site_doc.name = "site1.example.com"
		site_doc.cluster = "cluster1"
		site_doc.server = "srv1"
		site_doc.bench = "bench1"
		site_doc.release_group = "rg1"

		mock_db.get_value.return_value = "db-srv1"
		mock_db.count.return_value = 1  # another server still exists

		mock_server = MagicMock()
		mock_rg = MagicMock()
		mock_rg.servers = []

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Server":
				return mock_server
			if doctype == "Release Group":
				return mock_rg
			return MagicMock()

		mock_get_doc.side_effect = get_doc_side_effect

		from press.press.doctype.site.bizkit_archive import teardown_temporary_site
		teardown_temporary_site(site_doc)

		# DB server and cluster should NOT be deleted
		calls = [str(c) for c in mock_force_delete.call_args_list]
		assert not any("Database Server" in c for c in calls)
		assert not any("Cluster" in c for c in calls)


if __name__ == "__main__":
	unittest.main()
