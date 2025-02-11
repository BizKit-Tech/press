import os
import json
import paramiko
from datetime import datetime, timedelta

import frappe
from frappe.utils import now_datetime as now


MAX_DURATION = timedelta(hours=23, minutes=59, seconds=59)
ENV_ABBR = {
    "Development": "dev",
    "Production": "prod",
    "Demo": "demo",
}

# TODO: Add more steps to the Agent Job Type
# TODO: Assign values for the site_name, admin_password, company_name, and company_abbr

class SiteSetup:
    def __init__(self, server_name, verbose=False):
        self.server_name = server_name
        self.verbose = verbose
        self.get_app_server_details()
        self.get_database_server_details()

    def get_app_server_details(self):
        server_doc = frappe.get_doc("Server", self.server_name)
        self.server_ip = server_doc.ip
        self.server_username = server_doc.ssh_user
        self.server_port = server_doc.ssh_port or 22
        self.environment = server_doc.environment
        self.server_abbr = server_doc.hostname_abbreviation

    def get_database_server_details(self):
        db_server = frappe.db.get_value("Server", self.server_name, "database_server")
        db_server_doc = frappe.get_doc("Database Server", db_server)
        self.rds_endpoint = db_server_doc.ip
        self.db_user = "admin"
        self.db_root_password = db_server_doc.get_password("mariadb_root_password")
        self.db_name = f"db_server_doc.hostname_abbreviation_{ENV_ABBR[self.environment]}"

    def execute(self):
        frappe.msgprint("Site setup started.")
        self.create_agent_job_type()
        self.create_agent_job()
        self.setup_remote_connection()
        self.set_bench_path()
        self.update_apps()
        # more commands to be added here
        self.close_remote_connection()
        frappe.msgprint("Site setup completed. Please check the Agent Job for more details.")

    def create_agent_job_type(self):
        if frappe.db.exists("Agent Job Type", "Site Setup"):
            return

        doc = frappe.get_doc({
            "doctype": "Agent Job Type",
            "name": "Site Setup",
            "request_method": None,
            "request_path": None,
            "steps": [
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Update Apps"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Configure Database"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Disable Bench Watch"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Enable Automatic Bench Start"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Setup Production"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Create Site"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Set Developer Mode"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Restart Bench"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Remove Fail2Ban"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Run Initial Setup"
                },
            ],
            "disabled_auto_retry": 1,
        })
        doc.insert()

    def create_agent_job(self):
        self.agent_job = frappe.get_doc({
            "doctype": "Agent Job",
            "job_type": "Site Setup",
            "server_type": "Server",
            "server": self.server_name,
            "status": "Undelivered",
            "request_method": "POST",
            "request_path": "None",
            "request_data": json.dumps({}),
            "request_files": json.dumps({}),
            "output": "",
            "traceback": "",
        })
        self.agent_job.insert()

    def update_agent_job_step(self, step, output, traceback, start_time):
        doc = frappe.get_doc("Agent Job Step", {"step_name": step, "agent_job": self.agent_job.name})
        doc.duration = min(now() - start_time, MAX_DURATION)
        doc.output = output
        doc.traceback = traceback
        if traceback:
            doc.status = "Failure"
        else:
            doc.status = "Success"
        doc.save()

    def setup_remote_connection(self):
        pkey = paramiko.RSAKey.from_private_key_file(get_ssh_key())
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(self.server_ip, port=self.server_port, username=self.server_username, pkey=pkey)

    def close_remote_connection(self):
        self.client.close()

    def execute_commands(self, commands):
        output = ""
        traceback = ""

        for command in commands:
            _stdin, stdout, stderr = self.client.exec_command(command)
            output += stdout.read().decode()
            traceback += stderr.read().decode()

        return output, traceback

    def set_bench_path(self):
        self.frappe_bench_dir = "/home/ubuntu/frappe-bench"
        self.bench_path = "/home/ubuntu/.local/bin/bench"

    def update_apps(self):
        start_time = now()
        commands = [
            'echo "Updating apps..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && source env/bin/activate && pip install python-crontab)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} update --pull --requirements --no-backup)'
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Update Apps", output, traceback, start_time)

    def configure_database(self):
        start_time = now()
        commands = [
            'echo "Configuring database..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} set-config -g db_host {self.rds_endpoint})',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} set-config -g rds_db 1)',
            f'source ~/.profile && mysql -h {self.rds_endpoint} -u {self.db_user} -P 3306 -p{self.db_root_password} -e "CREATE DATABASE {self.db_name};"',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Configure Database", output, traceback, start_time)

    def disable_bench_watch(self):
        start_time = now()
        commands = [
            'echo "Disabling bench watch..."',
            f"source ~/.profile && sed -i 's/watch: bench watch/# watch: bench watch/' {self.frappe_bench_dir}/Procfile",
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Disable Bench Watch", output, traceback, start_time)

    def enable_automatic_bench_start(self):
        start_time = now()
        commands = [
            'echo "Enabling automatic bench start..."',
            'source ~/.profile && sudo systemctl enable bench-start.service',
            'source ~/.profile && sudo systemctl start bench-start.service',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)

    def setup_production(self):
        start_time = now()
        commands = [
            'echo "Setting up production..."',
            'source ~/.profile && sudo apt-get install -y python3-pip',
            'source ~/.profile && sudo pip3 install -e ~/.bench',
            f'source ~/.profile && sudo {self.frappe_bench_dir} setup production ubuntu --yes',
            'source ~/.profile && chmod 701 /home/ubuntu',
            f'source ~/.profile && sudo {self.frappe_bench_dir} setup production ubuntu --yes # For restarting services',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)

    def create_site(self):
        start_time = now()
        commands = [
            'echo "Creating site..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} new-site --db-name {self.db_name} --mariadb-root-username {self.db_user} --mariadb-root-password {self.db_root_password} --admin-password {admin_password} {site_name} --force)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {site_name} install-app erpnext --run-patches)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {site_name} install-app bizkit_core --run-patches)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} migrate --skip-failing) # Workaround: migrate and skip failing patches before running update to build prereqs first',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} update --patch --build --no-backup)',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)

    def set_developer_mode(self):
        start_time = now()
        commands = [
            'echo "Setting site to developer mode..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} set-config -g developer_mode 1)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} clear-cache)',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)

    def restart_bench(self):
        start_time = now()
        commands = [
            'echo "Restarting bench..."',
            'source ~/.profile && sudo systemctl restart bench-start.service',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)

    def remove_fail2ban(self):
        start_time = now()
        commands = [
            'echo "Removing fail2ban..."',
            'source ~/.profile && sudo apt-get remove --auto-remove fail2ban --yes',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)

    def run_initial_setup(self):
        start_time = now()
        commands = [
            'echo "Running initial setup..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} run-initial-setup --company-name "{company_name}" --company-abbreviation "{company_abbr}" --mariadb-root-login {self.db_user} --mariadb-root-password {self.db_root_password} --keep-active-domains --force-create-db)',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", output, traceback, start_time)


def get_ssh_key():
    ssh_key = frappe.db.get_single_value('Press Settings', 'default_ssh_key')
    file_path = os.path.join(frappe.utils.get_site_path(), ssh_key.lstrip("/"))

    return file_path