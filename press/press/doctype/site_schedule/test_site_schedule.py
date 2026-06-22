import frappe
import unittest


class TestSiteSchedule(unittest.TestCase):
	def setUp(self):
		self.preset = frappe.get_doc({
			"doctype": "Site Schedule Preset",
			"preset_name": "Test Schedule Preset",
			"monday": 1,
			"tuesday": 1,
			"wednesday": 1,
			"thursday": 1,
			"friday": 1,
			"saturday": 0,
			"sunday": 0,
			"all_day": 0,
			"start_time": "08:00:00",
			"stop_time": "18:00:00",
		})
		self.preset.insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Site Schedule Preset", self.preset.name, ignore_permissions=True)

	def test_site_schedule_creation(self):
		# Assumes a site named "test.localhost" exists in the test environment
		schedule = frappe.get_doc({
			"doctype": "Site Schedule",
			"site": frappe.get_all("Site", limit=1)[0].name if frappe.get_all("Site", limit=1) else "test.localhost",
			"enabled": 1,
			"preset": self.preset.name,
			"override": "None",
		})
		schedule.insert(ignore_permissions=True)
		self.assertEqual(schedule.enabled, 1)
		self.assertEqual(schedule.preset, self.preset.name)
		self.assertEqual(schedule.override, "None")
		frappe.delete_doc("Site Schedule", schedule.name, ignore_permissions=True)

	def test_override_until_datetime(self):
		site_name = frappe.get_all("Site", limit=1)[0].name if frappe.get_all("Site", limit=1) else "test.localhost"
		schedule = frappe.get_doc({
			"doctype": "Site Schedule",
			"site": site_name,
			"enabled": 1,
			"preset": self.preset.name,
			"override": "Until Datetime",
			"override_until": "2026-12-31 23:59:59",
		})
		schedule.insert(ignore_permissions=True)
		self.assertEqual(schedule.override, "Until Datetime")
		self.assertIsNotNone(schedule.override_until)
		frappe.delete_doc("Site Schedule", schedule.name, ignore_permissions=True)

	def test_indefinite_override(self):
		site_name = frappe.get_all("Site", limit=1)[0].name if frappe.get_all("Site", limit=1) else "test.localhost"
		schedule = frappe.get_doc({
			"doctype": "Site Schedule",
			"site": site_name,
			"enabled": 0,
			"preset": self.preset.name,
			"override": "Indefinite",
		})
		schedule.insert(ignore_permissions=True)
		self.assertEqual(schedule.override, "Indefinite")
		self.assertEqual(schedule.enabled, 0)
		frappe.delete_doc("Site Schedule", schedule.name, ignore_permissions=True)
