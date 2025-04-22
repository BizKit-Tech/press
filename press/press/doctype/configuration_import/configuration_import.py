# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from press.api.client import dashboard_whitelist
from .sheet_importer import get_sheet_importer


class ConfigurationImport(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		configuration_type: DF.Literal["", "Roles and Permissions", "Field Properties", "Accounts Settings", "Buying Settings", "Selling Settings", "Stock Settings", "System Settings"]
		excel_file: DF.Attach | None
		google_sheet_access_status: DF.Literal["Not Tested", "Accessible", "Inaccessible"]
		google_sheet_url: DF.Data | None
		sheet_type: DF.Literal["", "Google Sheets", "Excel"]
		show_failed_logs: DF.Check
		site: DF.Link
		status: DF.Literal["Pending", "In Progress", "Success", "Partial Success", "Error"]
		template_warnings: DF.Code | None
	# end: auto-generated types

	dashboard_fields = ["configuration_type", "sheet_type", "status"]
	
	@frappe.whitelist()
	def test_google_sheet_permission(self):
		"""Test if the Google Sheet is accessible."""
		if self.sheet_type != "Google Sheets" and not self.google_sheet_url:
			return

		try:
			sheet_importer = get_sheet_importer("google", self.google_sheet_url)
			status = "Accessible"
		except:
			status = "Inaccessible"

		return status