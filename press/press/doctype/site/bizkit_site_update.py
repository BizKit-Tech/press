import os
import json
import paramiko
from datetime import datetime, timedelta
import boto3
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


class SiteUpdate:
    def __init__(self, site, verbose=False):
        self.site = site
        self.server_name = self.site.server
        self.bench = self.site.bench
        self.verbose = verbose
        self.get_app_server_details()
        self.set_bench_path()
        self.fail = False

    def get_app_server_details(self):
        server_doc = frappe.get_doc("Server", self.server_name)
        self.server_ip = server_doc.ip
        self.server_username = server_doc.ssh_user
        self.server_port = server_doc.ssh_port or 22
        self.environment = server_doc.environment
        self.server_abbr = server_doc.hostname_abbreviation.replace("-", "_")

    def execute(self):
        frappe.msgprint("Site update started.")
        self.create_agent_job_type()
        self.create_agent_job()
        self.setup_remote_connection()
        
        if self.client:
            self.enable_maintenance_mode()
            self.pull_changes()
            self.bench_build()
            self.bench_migrate()
            self.bench_restart()
            self.disable_maintenance_mode()
        
        self.update_agent_job_status()
        self.close_remote_connection()
        self.update_site_status()
        frappe.msgprint("Site update completed. Please check the Agent Job for more details.")

    def update_site_status(self):
        self.site.reload()
        if self.fail:
            self.site.status = "Broken"
        else:
            self.site.status = "Active"
        self.site.save()
        frappe.db.commit()

    def create_agent_job_type(self):
        if frappe.db.exists("Agent Job Type", "Update Site"):
            return

        doc = frappe.get_doc({
            "doctype": "Agent Job Type",
            "name": "Update Site",
            "request_method": None,
            "request_path": None,
            "steps": [
                {
                    "parent": "Update Site",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Enable Maintenance Mode"
                },
                {
                    "parent": "Update Site",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Pull Changes"
                },
                {
                    "parent": "Update Site",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Bench Build"
                },
                {
                    "parent": "Update Site",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Bench Migrate"
                },
                {
                    "parent": "Update Site",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Bench Restart"
                },
                {
                    "parent": "Update Site",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Disable Maintenance Mode"
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
            "job_type": "Update Site",
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

    def enable_maintenance_mode(self):
        start_time = now()
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} set-maintenance-mode on",
            f"cd {self.frappe_bench_dir} && {self.bench_path} clear-cache"
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Maintenance Mode", start_time, output, traceback)

    def pull_changes(self):
        start_time = now()
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} update --pull --no-backup",
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Pull Changes", start_time, output, traceback)

    def bench_build(self):
        start_time = now()
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} build",
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Bench Build", start_time, output, traceback)

    def bench_migrate(self):
        start_time = now()
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} migrate",
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Bench Migrate", start_time, output, traceback)

    def bench_restart(self):
        start_time = now()

        if self.environment != "Production":
            self.update_agent_job_step("Bench Restart", start_time, skipped=True)
            return
        
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} restart",
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Bench Restart", start_time, output, traceback)

    def disable_maintenance_mode(self):
        start_time = now()
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} set-maintenance-mode off",
            f"cd {self.frappe_bench_dir} && {self.bench_path} clear-cache"
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Disable Maintenance Mode", start_time, output, traceback)

    def set_automatic_updates_in_site(self, update_enabled):
        self.setup_remote_connection()
        
        if not self.client:
            frappe.msgprint("Failed to connect to the server for setting automatic updates.", alert=True, indicator="red")
            return
        
        commands = [
            f"cd {self.frappe_bench_dir} && {self.bench_path} set-config auto_updates_enabled {update_enabled}",
            f"cd {self.frappe_bench_dir} && {self.bench_path} clear-cache"
        ]
        output, traceback = self.execute_commands(commands)
        
        if output["exit_status"] != 0:
            frappe.msgprint("Failed to set automatic updates in site.", alert=True, indicator="red")
            return
        
        frappe.msgprint(
            f"Automatic updates {'enabled' if update_enabled else 'disabled'} for site {self.site.name}.",
            alert=True,
            indicator="green" if update_enabled else "orange"
        )


def get_ssh_key():
    ssh_key = frappe.db.get_single_value('Press Settings', 'default_ssh_key')
    file_path = os.path.join(frappe.utils.get_site_path(), ssh_key.lstrip("/"))

    return file_path