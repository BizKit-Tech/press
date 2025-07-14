# Copyright (c) 2020, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import re
import json
import paramiko
from typing import TYPE_CHECKING

import frappe
from frappe.desk.doctype.tag.tag import add_tag
from frappe.model.document import Document

from press.agent import Agent
from press.utils import log_error

import boto3
import io

if TYPE_CHECKING:
	from datetime import datetime


class SiteBackup(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		config_file: DF.Data | None
		config_file_size: DF.Data | None
		config_file_url: DF.Text | None
		database: DF.Data | None
		database_file: DF.Data | None
		database_size: DF.Data | None
		database_url: DF.Text | None
		files_availability: DF.Literal["", "Available", "Unavailable"]
		job: DF.Link | None
		offsite: DF.Check
		offsite_backup: DF.Code | None
		private_file: DF.Data | None
		private_size: DF.Data | None
		private_url: DF.Text | None
		public_file: DF.Data | None
		public_size: DF.Data | None
		public_url: DF.Text | None
		remote_config_file: DF.Link | None
		remote_database_file: DF.Link | None
		remote_private_file: DF.Link | None
		remote_public_file: DF.Link | None
		site: DF.Link
		size: DF.Data | None
		status: DF.Literal["Pending", "Running", "Success", "Failure"]
		team: DF.Link | None
		url: DF.Data | None
		with_files: DF.Check
	# end: auto-generated types

	dashboard_fields = (
		"name",
		"job",
		"status",
		"database_url",
		"public_url",
		"private_url",
		"config_file_url",
		"site",
		"database_size",
		"public_size",
		"private_size",
		"with_files",
		"offsite",
		"files_availability",
		"remote_database_file",
		"remote_public_file",
		"remote_private_file",
		"remote_config_file",
	)

	def before_insert(self):
		if getattr(self, "force", False):
			return
		two_hours_ago = frappe.utils.add_to_date(None, hours=-2)
		if frappe.db.count(
			"Site Backup",
			{
				"site": self.site,
				"status": ("in", ["Running", "Pending"]),
				"creation": (">", two_hours_ago),
			},
		):
			frappe.throw("Too many pending backups")

	def after_insert(self):
		self.backup_job()
		# site = frappe.get_doc("Site", self.site)
		# agent = Agent(site.server)
		# job = agent.backup_site(site, self.with_files, self.offsite)
		# frappe.db.set_value("Site Backup", self.name, "job", job.name)

	def after_delete(self):
		if self.job:
			frappe.delete_doc_if_exists("Agent Job", self.job)

	@classmethod
	def offsite_backup_exists(cls, site: str, day: datetime.date) -> bool:
		return cls.backup_exists(site, day, {"offsite": True})

	@classmethod
	def backup_exists(cls, site: str, day: datetime.date, filters: dict):
		base_filters = {
			"creation": ("between", [day, day]),
			"site": site,
			"status": "Success",
		}
		return frappe.get_all("Site Backup", {**base_filters, **filters})

	@classmethod
	def file_backup_exists(cls, site: str, day: datetime.date) -> bool:
		return cls.backup_exists(site, day, {"with_files": True})
	
	# BizKit Backup Job
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
			log_error("Site Backup Error: Failed to connect to server", data=e)

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

	def backup_job(self):
		"""Queue the backup process."""
		frappe.enqueue_doc(
			self.doctype, self.name, "_backup_job", queue="long", timeout=7200
		)

	def _backup_job(self):
		self.setup_remote_connection()

		frappe_bench_dir = "/home/ubuntu/frappe-bench"
		bench_path = "/home/ubuntu/.local/bin/bench"

		with_files = "--with-files --compress" if self.with_files else ""

		commands = [
			f'source ~/.profile && (cd {frappe_bench_dir} && {bench_path} backup {with_files})',
		]

		output, traceback = self.execute_commands(commands)

		self.status = "Success"
		self.files_availability = "Available"
		backup_details = parse_backup_details(output["message"])
		self.update({
			"database_size": backup_details["database"]["size"],
			"database_file": backup_details["database"]["file"],
			"private_size": backup_details.get("private", {}).get("size", 0),
			"private_file": backup_details.get("private", {}).get("file", ""),
			"public_size": backup_details.get("public", {}).get("size", 0),
			"public_file": backup_details.get("public", {}).get("file", ""),
			"config_file_size": backup_details.get("config", {}).get("size", 0),
			"config_file": backup_details.get("config", {}).get("file", "")
		})

		self.upload_offsite_backup(backup_details)

		self.close_remote_connection()
		
		if output["exit_status"] != 0:
			self.status = "Failure"

		self.save()

		frappe.logger().error(traceback)

	def upload_offsite_backup(self, backup_files):
		file_type_field = {
			"database": "database_url",
			"config": "config_file_url",
			"public": "public_url",
			"private": "private_url",
		}

		backup_settings = frappe.get_single("Press Settings")
		access_key = backup_settings.offsite_backups_access_key_id
		secret_key = backup_settings.get_password("offsite_backups_secret_access_key")
		bucket = backup_settings.aws_s3_bucket
		backup_count = backup_settings.offsite_backups_count
		file_types = ["database", "site_config_backup", "files", "private-files"]

		offsite_files = {}

		s3 = boto3.client(
			"s3",
			aws_access_key_id=access_key,
			aws_secret_access_key=secret_key,
		)

		for key, backup_file in backup_files.items():			
			file_name = backup_file["file"].split(os.sep)[-1]
			fodler_name = self.site
			offsite_path = os.path.join(fodler_name, file_name)
			offsite_files[file_name] = offsite_path
			region = "ap-southeast-1"

			try:
				sftp = self.client.open_sftp()
				file_path = os.path.join("./frappe-bench/sites", *backup_file["file"].split(os.sep)[1:])
				remote_file = sftp.file(file_path, "rb")
				file_data = remote_file.read()
				remote_file.close()
				sftp.close()
				s3.upload_fileobj(io.BytesIO(file_data), bucket, offsite_path)

				self.update({
					file_type_field[key]: f"https://{bucket}.s3.{region}.amazonaws.com/{fodler_name}/{file_name}"
				})
			except Exception as e:
				frappe.logger().error(f"Failed to upload {file_name} to S3 bucket {bucket}: {str(e)}")
				raise e
		
		self.offsite = 1
			
		maintain_s3_file_limit(s3, bucket, fodler_name, file_types, backup_count)

def track_offsite_backups(site: str, backup_data: dict, offsite_backup_data: dict) -> tuple:
	remote_files = {"database": None, "site_config": None, "public": None, "private": None}

	if offsite_backup_data:
		bucket = get_backup_bucket(frappe.db.get_value("Site", site, "cluster"))
		for type, backup in backup_data.items():
			file_name, file_size = backup["file"], backup["size"]
			file_path = offsite_backup_data.get(file_name)

			file_types = {
				"database": "application/x-gzip",
				"site_config": "application/json",
			}
			if file_path:
				remote_file = frappe.get_doc(
					{
						"doctype": "Remote File",
						"site": site,
						"file_name": file_name,
						"file_path": file_path,
						"file_size": file_size,
						"file_type": file_types.get(type, "application/x-tar"),
						"bucket": bucket,
					}
				)
				remote_file.save()
				add_tag("Offsite Backup", remote_file.doctype, remote_file.name)
				remote_files[type] = remote_file.name

	return (
		remote_files["database"],
		remote_files["site_config"],
		remote_files["public"],
		remote_files["private"],
	)


def process_backup_site_job_update(job):
	backups = frappe.get_all("Site Backup", fields=["name", "status"], filters={"job": job.name}, limit=1)
	if not backups:
		return
	backup = backups[0]
	if job.status != backup.status:
		status = job.status
		if job.status == "Delivery Failure":
			status = "Failure"

		frappe.db.set_value("Site Backup", backup.name, "status", status)
		if job.status == "Success":
			job_data = json.loads(job.data)
			backup_data, offsite_backup_data = job_data["backups"], job_data["offsite"]
			(
				remote_database,
				remote_config_file,
				remote_public,
				remote_private,
			) = track_offsite_backups(job.site, backup_data, offsite_backup_data)

			site_backup_dict = {
				"files_availability": "Available",
				"database_size": backup_data["database"]["size"],
				"database_url": backup_data["database"]["url"],
				"database_file": backup_data["database"]["file"],
				"remote_database_file": remote_database,
			}

			if "site_config" in backup_data:
				site_backup_dict.update(
					{
						"config_file_size": backup_data["site_config"]["size"],
						"config_file_url": backup_data["site_config"]["url"],
						"config_file": backup_data["site_config"]["file"],
						"remote_config_file": remote_config_file,
					}
				)

			if "private" in backup_data and "public" in backup_data:
				site_backup_dict.update(
					{
						"private_size": backup_data["private"]["size"],
						"private_url": backup_data["private"]["url"],
						"private_file": backup_data["private"]["file"],
						"remote_public_file": remote_public,
						"public_size": backup_data["public"]["size"],
						"public_url": backup_data["public"]["url"],
						"public_file": backup_data["public"]["file"],
						"remote_private_file": remote_private,
					}
				)

			frappe.db.set_value("Site Backup", backup.name, site_backup_dict)


def get_backup_bucket(cluster, region=False):
	bucket_for_cluster = frappe.get_all("Backup Bucket", {"cluster": cluster}, ["name", "region"], limit=1)
	default_bucket = frappe.db.get_single_value("Press Settings", "aws_s3_bucket")

	if region:
		return bucket_for_cluster[0] if bucket_for_cluster else default_bucket
	return bucket_for_cluster[0]["name"] if bucket_for_cluster else default_bucket


def on_doctype_update():
	frappe.db.add_index("Site Backup", ["files_availability", "job"])


def get_ssh_key():
	ssh_key = frappe.db.get_single_value('Press Settings', 'default_ssh_key')
	file_path = os.path.join(frappe.utils.get_site_path(), ssh_key.lstrip("/"))

	return file_path


def parse_backup_details(output):
	pattern = r'^(Config|Database|Public|Private)\s*:\s+(\S+)\s+(\d+(?:\.\d+)?(?:[KMG]?i?B))$'

	parsed = {}
	for line in output.strip().splitlines():
		match = re.match(pattern, line.strip())
		if match:
			file_type, file_path, file_size = match.groups()
			parsed[file_type.lower()] = {
				'file': file_path,
				'size': file_size
			}
	
	return parsed


def maintain_s3_file_limit(s3_client, bucket, prefix, file_types, max_files):
	response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
	files = response.get('Contents', [])

	for file_type in file_types:
		matching_files = []
		for obj in files:
			name = obj['Key'].split('/')[-1]
			match = re.match(r'^\d{8}_\d{6}-[^-]+-(.+?)\.', name)
			if match and match.group(1) == file_type:
				matching_files.append(obj)

		if len(matching_files) > max_files:
			# Sort by LastModified (oldest first)
			matching_files.sort(key=lambda x: x['LastModified'])
			to_delete = matching_files[:len(matching_files) - max_files]

			for obj in to_delete:
				frappe.logger().info(f"Deleting old {file_type} file: {obj['Key']}")
				s3_client.delete_object(Bucket=bucket, Key=obj['Key'])