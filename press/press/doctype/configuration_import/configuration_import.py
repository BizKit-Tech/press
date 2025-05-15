# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import frappe
import paramiko
import os
import re
import json
from frappe.model.document import Document

from .sheet_importer import get_sheet_importer


class ConfigurationImport(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		configuration_type: DF.Literal["", "Roles and Permissions", "Field Properties", "Accounts Settings", "Buying Settings", "Selling Settings", "Stock Settings", "HR Settings", "Payroll Settings", "System Settings"]
		excel_file: DF.Attach | None
		google_sheet_access_status: DF.Literal["Not Tested", "Accessible", "Inaccessible"]
		google_sheet_url: DF.Data | None
		import_log: DF.Code | None
		sheet_type: DF.Literal["", "Google Sheets", "Excel"]
		show_failed_logs: DF.Check
		site: DF.Link
		status: DF.Literal["Pending", "In Progress", "Success", "Partial Success", "Error"]
		template_warnings: DF.Code | None
	# end: auto-generated types

	dashboard_fields = ["site", "configuration_type", "sheet_type", "status"]

	def after_insert(self):
		if self.status == "Pending":
			self.start_import()

	def setup_remote_connection(self):
		site = frappe.get_doc("Site", self.site)
		server = frappe.get_doc("Server", site.server)
		server_ip = server.ip
		server_port = server.ssh_port or 22
		server_username = server.ssh_user or "ubuntu"

		try:
			pkey = paramiko.RSAKey.from_private_key_file(get_ssh_key())
			self.client = paramiko.SSHClient()
			self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			self.client.connect(server_ip, port=server_port, username=server_username, pkey=pkey)
		except Exception as e:
			self.fail = True
			self.client = 0
			print("Site Setup Error: Failed to connect to server", data=e)

	def close_remote_connection(self):
		if self.client:
			self.client.close()

	def execute_commands(self, commands):
		output = {"message": "", "exit_status": 0}
		traceback = ""

		for command in commands:
			_stdin, stdout, stderr = self.client.exec_command(command)
			output["message"] += stdout.read().decode()
			traceback += stderr.read().decode()
			exit_status = stdout.channel.recv_exit_status()
			if exit_status != 0:
				output["exit_status"] = exit_status
				break

		return output, traceback
	
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
	 
	@frappe.whitelist()
	def start_import(self):
		"""Queue the import process."""
		frappe.enqueue_doc(
			self.doctype, self.name, "_start_import", queue="short", timeout=300
		)
		
	def _start_import(self):
		"""Import configuration from the selected sheet."""

		self.setup_remote_connection()
		
		import_functions_map = {
			"Roles and Permissions": "import-role-permissions",
			"Field Properties": "import-custom-properties",
			"Accounts Settings": "import-settings",
			"Buying Settings": "import-settings",
			"Selling Settings": "import-settings",
			"Stock Settings": "import-settings",
			"System Settings": "import-settings",
			"HR Settings": "import-settings",
			"Payroll Settings": "import-settings",
		}

		frappe_bench_dir = "/home/ubuntu/frappe-bench"
		bench_path = "/home/ubuntu/.local/bin/bench"

		sheet_type = self.sheet_type.lower() if self.sheet_type == "Excel" else "google"
		sheet_location = self.google_sheet_url if self.sheet_type == "Google Sheets" else self.excel_file

		commands = [
			f'source ~/.profile && (cd {frappe_bench_dir} && {bench_path} {import_functions_map[self.configuration_type]} --sheet-type {sheet_type} --sheet-location {sheet_location})',
		]

		if self.configuration_type == "Field Properties":
			commands.append(f'source ~/.profile && (cd {frappe_bench_dir} && {bench_path} clear-cache)')

		output, traceback = self.execute_commands(commands)

		self.close_remote_connection()

		parsed_logs = parse_and_group_entries(output["message"].split("\n"))
		self.import_log = json.dumps(parsed_logs, indent=2)

		if evaluate_status_distribution(parsed_logs) == "all error" or output["exit_status"] != 0:
			self.status = "Error"
		elif evaluate_status_distribution(parsed_logs) == "all success":
			self.status = "Success"
		elif evaluate_status_distribution(parsed_logs) == "mixed":
			self.status = "Partial Success"
		
		self.save()

		frappe.logger().error(traceback)

		frappe.msgprint("Import completed successfully." if self.status == "Success" else "Import failed. Please check the logs for more details.")


def get_ssh_key():
	ssh_key = frappe.db.get_single_value('Press Settings', 'default_ssh_key')
	file_path = os.path.join(frappe.utils.get_site_path(), ssh_key.lstrip("/"))

	return file_path


# Regex to match ANSI escape sequences like \033[92m
ANSI_ESCAPE = re.compile(r'\x1B\[[0-9;]*[A-Za-z]')

def strip_ansi_codes(text):
    return ANSI_ESCAPE.sub('', text)


def parse_log_entry(log_entry):
	clean_entry = strip_ansi_codes(log_entry)
	pattern = r"\[(Row|DocType|File) ([^\]]+)\]\[(\w+)\] (.+)"
	match = re.match(pattern, clean_entry)
	if match:
		entity_type = match.group(1)
		row_number = match.group(2)
		status = match.group(3)
		message = match.group(4)
		return {
			"entity_type": entity_type,
			"row": row_number,
			"status": status,
			"message": message
		}
	else:
		raise ValueError(f"Invalid log entry format: {clean_entry}")


def parse_and_group_entries(log_entries):
	grouped = {}
	for entry in log_entries:
		try:
			parsed = parse_log_entry(entry)
			key = parsed["message"]
			if key not in grouped:
				grouped[key] = {
					"entity_type": parsed["entity_type"],
					"row": parsed["row"],
					"status": parsed["status"],
					"message": parsed["message"]
				}
			else:
				grouped[key]["row"] += f", {str(parsed['row'])}"
		except ValueError as e:
			print(e)
			continue
	return list(grouped.values())


def evaluate_status_distribution(entries):
	statuses = set(entry["status"].lower() for entry in entries)

	if statuses == {"success"}:
		return "all success"
	elif statuses == {"error"}:
		return "all error"
	else:
		return "mixed"