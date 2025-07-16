import os
import json
import paramiko
import boto3
from datetime import datetime, timedelta
from urllib.parse import urlparse, unquote

import frappe
from frappe.utils import now_datetime as now
from press.utils import log_error


MAX_DURATION = timedelta(hours=23, minutes=59, seconds=59)
ENV_ABBR = {
    "Development": "dev",
    "Production": "prod",
    "Demo": "demo",
}


class BackupRestore:
    def __init__(self, site, verbose=False):
        self.site = site
        self.server_name = self.site.server
        self.bench = self.site.bench
        self.verbose = verbose
        self.get_app_server_details()
        self.get_database_server_details()
        self.fail = False

    def get_app_server_details(self):
        server_doc = frappe.get_doc("Server", self.server_name)
        self.server_ip = server_doc.ip
        self.server_username = server_doc.ssh_user
        self.server_port = server_doc.ssh_port or 22
        self.environment = server_doc.environment
        self.server_abbr = server_doc.hostname_abbreviation.replace("-", "_")

    def get_database_server_details(self):
        db_server = frappe.db.get_value("Server", self.server_name, "database_server")
        db_server_doc = frappe.get_doc("Database Server", db_server)
        self.rds_endpoint = db_server_doc.ip
        self.db_user = "admin"
        self.db_root_password = db_server_doc.get_password("mariadb_root_password")
        self.db_name = f"{db_server_doc.hostname_abbreviation}_{ENV_ABBR[self.environment]}".replace("-", "_")

    def execute(self):
        frappe.msgprint("Backup restore started.")
        self.create_agent_job_type()
        self.create_agent_job()
        self.setup_remote_connection()

        if self.client:
            self.set_bench_path()
            self.download_backup()
            self.restore()

        self.update_agent_job_status()
        self.close_remote_connection()
        self.update_site_status()
        frappe.msgprint("Backup restore completed. Please check the Agent Job for more details.")

    def update_site_status(self):
        self.site.reload()
        if self.fail:
            self.site.status = "Broken"
        else:
            self.site.status = "Active"
        self.site.save()
        frappe.db.commit()

    def create_agent_job_type(self):
        if frappe.db.exists("Agent Job Type", "Restore Backup"):
            return

        doc = frappe.get_doc({
            "doctype": "Agent Job Type",
            "name": "Restore Backup",
            "request_method": None,
            "request_path": None,
            "steps": [
                {
                    "parent": "Restore Backup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Download Backup"
                },
                {
                    "parent": "Restore Backup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Restore Backup"
                },
            ],
            "disabled_auto_retry": 1,
        })
        doc.insert()
        frappe.db.commit()

    def create_agent_job(self):
        self.start_time = now()
        self.agent_job = frappe.get_doc({
            "doctype": "Agent Job",
            "job_type": "Restore Backup",
            "server_type": "Server",
            "server": self.server_name,
            "start": self.start_time,
            "status": "Running",
            "request_method": "POST",
            "request_path": "None",
            "request_data": json.dumps({}),
            "request_files": json.dumps({}),
            "output": "",
            "traceback": "",
            "site": self.site.name,
            "bench": self.bench,
        })
        self.agent_job.insert()
        frappe.db.commit()

    def update_agent_job_status(self):
        self.agent_job.reload()
        self.agent_job.status = "Failure" if self.fail else "Success"
        self.agent_job.end = now()
        self.agent_job.duration = min(self.agent_job.end - self.start_time, MAX_DURATION)
        self.agent_job.save()
        frappe.db.commit()

    def update_agent_job_step(self, step, start_time, output=None, traceback=None, skipped=False):
        doc = frappe.get_doc("Agent Job Step", {"step_name": step, "agent_job": self.agent_job.name})
        doc.duration = min(now() - start_time, MAX_DURATION)
        if skipped:
            doc.status = "Skipped"
        else:
            doc.output = output["message"]
            doc.traceback = traceback
            doc.status = "Success"
            if output["exit_status"] != 0:
                self.fail = True
                doc.status = "Failure"
        doc.save()
        frappe.db.commit()

    def setup_remote_connection(self):
        try:
            pkey = paramiko.RSAKey.from_private_key_file(get_ssh_key())
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.server_ip, port=self.server_port, username=self.server_username, pkey=pkey)
        except Exception as e:
            self.fail = True
            self.client = 0
            log_error("Site Setup Error: Failed to connect to server", data=e)

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

    def set_bench_path(self):
        self.frappe_bench_dir = "/home/ubuntu/frappe-bench"
        self.bench_path = "/home/ubuntu/.local/bin/bench"

    def download_backup(self):
        start_time = now()

        commands = [
            'echo "Downloading backup files..."',
        ]

        backup_doc = frappe.get_doc("Site Backup", self.site.restored_from_backup)
        db_backup = backup_doc.database_url
        config_file_backup = backup_doc.config_file_url
        public_files_backup = backup_doc.public_url
        private_files_backup = backup_doc.private_url

        backup_files = []

        if db_backup:
            commands.append(f'cd {self.frappe_bench_dir} && wget {db_backup}')
            self.db_backup_path = db_backup.split("/")[-1]
            backup_files.append(db_backup)

        if config_file_backup:
            commands.append(f'cd {self.frappe_bench_dir} && wget {config_file_backup}')
            self.config_path = config_file_backup.split("/")[-1]
            backup_files.append(config_file_backup)
        
        if public_files_backup:
            commands.append(f'cd {self.frappe_bench_dir} && wget {public_files_backup}')
            self.public_path = public_files_backup.split("/")[-1]
            backup_files.append(public_files_backup)

        if private_files_backup:
            commands.append(f'cd {self.frappe_bench_dir} && wget {private_files_backup}')
            self.private_path = private_files_backup.split("/")[-1]
            backup_files.append(private_files_backup)

        list_files = f'source ~/.profile && (cd {self.frappe_bench_dir} && ls -lh)'
        commands.append(list_files)

        try:
            s3 = setup_s3_client()
            for file_url in backup_files:
                change_file_permissions(s3, file_url, "public-read")
        except Exception as e:
            self.fail = True
            output = {"message": "", "exit_status": 1}
            traceback = f"Failed to change file permissions: {e}"
        else:
            output, traceback = self.execute_commands(commands)

            for file_url in backup_files:
                change_file_permissions(s3, file_url, "private")
        
        self.update_agent_job_step("Download Backup", start_time, output, traceback)

    def restore(self):
        start_time = now()
        admin_password = self.site.get_password("admin_password")
        
        public_file_option = f"--with-public-files {self.public_path}" if self.public_path else ""
        private_file_option = f"--with-private-files {self.private_path} " if self.private_path else ""
        
        commands = [
            'echo "Restoring backup..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} --force restore --mariadb-root-username {self.db_user} --mariadb-root-password {self.db_root_password} --admin-password {admin_password} {public_file_option} {private_file_option} {self.db_backup_path})',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} set-admin-password {admin_password})',
        ]

        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Restore Backup", start_time, output, traceback)


def get_ssh_key():
    ssh_key = frappe.db.get_single_value('Press Settings', 'default_ssh_key')
    file_path = os.path.join(frappe.utils.get_site_path(), ssh_key.lstrip("/"))

    return file_path


def setup_s3_client():
    backup_settings = frappe.get_single("Press Settings")
    access_key = backup_settings.offsite_backups_access_key_id
    secret_key = backup_settings.get_password("offsite_backups_secret_access_key")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    
    return s3


def change_file_permissions(s3, object_url, object_acl):
    parsed_url = urlparse(object_url)

    domain_parts = parsed_url.netloc.split('.')
    if "s3" not in domain_parts:
        raise ValueError("URL is not a standard S3 URL.")

    bucket_name = domain_parts[0]
    object_key = unquote(parsed_url.path.lstrip('/'))

    s3.put_object_acl(Bucket=bucket_name, Key=object_key, ACL=object_acl)