import frappe
import unittest
from unittest.mock import patch


class TestSiteScheduleMethods(unittest.TestCase):
	def setUp(self):
		# Create a minimal preset
		if not frappe.db.exists("Site Schedule Preset", "Test Preset"):
			frappe.get_doc({
				"doctype": "Site Schedule Preset",
				"preset_name": "Test Preset",
				"monday": 1, "tuesday": 1, "wednesday": 1,
				"thursday": 1, "friday": 1,
				"saturday": 0, "sunday": 0,
				"all_day": 1,
			}).insert(ignore_permissions=True)

	def _get_dev_site(self):
		# Get a site on a Development or Demo server
		site_name = frappe.db.get_value(
			"Site",
			{"status": ["in", ["Active", "Inactive"]]},
			"name",
			order_by="creation desc"
		)
		if not site_name:
			self.skipTest("No suitable site found for testing")
		server_env = frappe.db.get_value(
			"Server",
			frappe.db.get_value("Site", site_name, "server"),
			"environment"
		)
		if server_env == "Production":
			self.skipTest("Test site is on Production server — scheduling blocked")
		return frappe.get_doc("Site", site_name)

	def test_set_schedule_creates_site_schedule(self):
		site = self._get_dev_site()
		# Clean up any pre-existing schedule
		if frappe.db.exists("Site Schedule", {"site": site.name}):
			frappe.delete_doc("Site Schedule", frappe.db.get_value("Site Schedule", {"site": site.name}), ignore_permissions=True)

		site.set_schedule("Test Preset")
		schedule = frappe.db.get_value("Site Schedule", {"site": site.name}, ["enabled", "preset"], as_dict=True)
		self.assertIsNotNone(schedule)
		self.assertEqual(schedule.enabled, 1)
		self.assertEqual(schedule.preset, "Test Preset")
		frappe.delete_doc("Site Schedule", frappe.db.get_value("Site Schedule", {"site": site.name}), ignore_permissions=True)

	def test_disable_schedule(self):
		site = self._get_dev_site()
		site.set_schedule("Test Preset")
		site.disable_schedule()
		enabled = frappe.db.get_value("Site Schedule", {"site": site.name}, "enabled")
		self.assertEqual(enabled, 0)
		frappe.delete_doc("Site Schedule", frappe.db.get_value("Site Schedule", {"site": site.name}), ignore_permissions=True)

	def test_set_schedule_override_indefinite(self):
		site = self._get_dev_site()
		site.set_schedule("Test Preset")
		site.set_schedule_override("Indefinite")
		override = frappe.db.get_value("Site Schedule", {"site": site.name}, "override")
		self.assertEqual(override, "Indefinite")
		frappe.delete_doc("Site Schedule", frappe.db.get_value("Site Schedule", {"site": site.name}), ignore_permissions=True)

	def test_set_schedule_override_until_datetime_requires_future_date(self):
		site = self._get_dev_site()
		site.set_schedule("Test Preset")
		with self.assertRaises(frappe.ValidationError):
			site.set_schedule_override("Until Datetime", "2020-01-01 00:00:00")
		frappe.delete_doc("Site Schedule", frappe.db.get_value("Site Schedule", {"site": site.name}), ignore_permissions=True)

	def test_get_schedule_returns_none_when_no_schedule(self):
		site = self._get_dev_site()
		if frappe.db.exists("Site Schedule", {"site": site.name}):
			frappe.delete_doc("Site Schedule", frappe.db.get_value("Site Schedule", {"site": site.name}), ignore_permissions=True)
		result = site.get_schedule()
		self.assertIsNone(result)

	def test_set_schedule_blocked_on_production(self):
		prod_server = frappe.db.get_value("Server", {"environment": "Production"}, "name")
		if not prod_server:
			self.skipTest("No Production server found")
		prod_site_name = frappe.db.get_value("Site", {"server": prod_server, "status": "Active"}, "name")
		if not prod_site_name:
			self.skipTest("No active site on Production server found")
		site = frappe.get_doc("Site", prod_site_name)
		with self.assertRaises(frappe.ValidationError):
			site.set_schedule("Test Preset")

	def tearDown(self):
		if frappe.db.exists("Site Schedule Preset", "Test Preset"):
			frappe.delete_doc("Site Schedule Preset", "Test Preset", ignore_permissions=True)
