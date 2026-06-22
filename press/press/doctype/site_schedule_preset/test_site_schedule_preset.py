import frappe
import unittest


class TestSiteSchedulePreset(unittest.TestCase):
	def test_preset_creation(self):
		preset = frappe.get_doc({
			"doctype": "Site Schedule Preset",
			"preset_name": "Test Hours",
			"monday": 1,
			"tuesday": 1,
			"wednesday": 0,
			"thursday": 0,
			"friday": 0,
			"saturday": 0,
			"sunday": 0,
			"all_day": 0,
			"start_time": "09:00:00",
			"stop_time": "17:00:00",
		})
		preset.insert(ignore_permissions=True)
		self.assertEqual(preset.preset_name, "Test Hours")
		self.assertEqual(preset.monday, 1)
		self.assertEqual(preset.start_time, "09:00:00")
		frappe.delete_doc("Site Schedule Preset", preset.name, ignore_permissions=True)

	def test_all_day_preset(self):
		preset = frappe.get_doc({
			"doctype": "Site Schedule Preset",
			"preset_name": "Test All Day",
			"monday": 1, "tuesday": 1, "wednesday": 1,
			"thursday": 1, "friday": 1, "saturday": 1, "sunday": 1,
			"all_day": 1,
		})
		preset.insert(ignore_permissions=True)
		self.assertEqual(preset.all_day, 1)
		frappe.delete_doc("Site Schedule Preset", preset.name, ignore_permissions=True)
