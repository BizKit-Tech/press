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
DEFAULT_APPS = ["frappe", "erpnext", "bizkit_core"]


class SiteSetup:
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
        frappe.msgprint("Site setup started.")
        self.create_agent_job_type()
        self.create_agent_job()
        self.setup_remote_connection()
        
        if self.client:
            self.set_bench_path()
            self.update_apps()
            self.configure_database()
            self.disable_bench_watch()
            self.enable_automatic_bench_start()
            self.setup_production()
            self.download_backup()
            self.create_site()
            self.restore_files()
            self.install_additional_apps()
            self.set_developer_mode()
            self.restart_bench()
            self.remove_fail2ban()
            self.run_initial_setup()
        
        self.update_agent_job_status()
        self.close_remote_connection()
        self.update_site_status()
        frappe.msgprint("Site setup completed. Please check the Agent Job for more details.")

    def update_site_status(self):
        self.site.reload()
        if self.fail:
            self.site.status = "Broken"
        else:
            self.site.status = "Active"
            self.site.setup_wizard_complete = 1
        self.site.save()
        frappe.db.commit()

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
                    "step_name": "Download Backup"
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
                    "step_name": "Restore Files"
                },
                {
                    "parent": "Site Setup",
                    "parentfield": "steps",
                    "parenttype": "Agent Job Type",
                    "step_name": "Install Additional Apps"
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
        frappe.db.commit()

    def create_agent_job(self):
        self.start_time = now()
        self.agent_job = frappe.get_doc({
            "doctype": "Agent Job",
            "job_type": "Site Setup",
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

    def update_apps(self):
        start_time = now()
        commands = [
            'echo "Updating apps..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && source env/bin/activate && pip install python-crontab)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} update --pull --requirements --no-backup)',
            f'source ~/.profile && (cd {self.frappe_bench_dir}/apps/frappe && sudo yarn install)',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Update Apps", start_time, output, traceback)

    def configure_database(self):
        start_time = now()
        commands = [
            'echo "Configuring database..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} set-config -g db_host {self.rds_endpoint})',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} set-config -g rds_db 1)',
            f'source ~/.profile && mysql -h {self.rds_endpoint} -u {self.db_user} -P 3306 -p{self.db_root_password} -e "CREATE DATABASE IF NOT EXISTS {self.db_name};"',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Configure Database", start_time, output, traceback)

    def disable_bench_watch(self):
        start_time = now()
        
        if self.environment == "Production":
            self.update_agent_job_step("Disable Bench Watch", start_time, skipped=True)
            return
        
        commands = [
            'echo "Disabling bench watch..."',
            f"source ~/.profile && sed -i 's/watch: bench watch/# watch: bench watch/' {self.frappe_bench_dir}/Procfile",
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Disable Bench Watch", start_time, output, traceback)

    def enable_automatic_bench_start(self):
        start_time = now()
        
        if self.environment == "Production":
            self.update_agent_job_step("Enable Automatic Bench Start", start_time, skipped=True)
            return
        
        commands = [
            'echo "Enabling automatic bench start..."',
            'source ~/.profile && sudo systemctl enable bench-start.service',
            'source ~/.profile && sudo systemctl start bench-start.service',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Enable Automatic Bench Start", start_time, output, traceback)

    def setup_production(self):
        start_time = now()
        
        if self.environment != "Production":
            self.update_agent_job_step("Setup Production", start_time, skipped=True)
            return
        
        commands = [
            'echo "Setting up production..."',
            'source ~/.profile && sudo apt-get install -y python3-pip',
            'source ~/.profile && sudo pip3 install -e ~/.bench',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && sudo {self.bench_path} setup production ubuntu --yes)',
            'source ~/.profile && chmod 701 /home/ubuntu',
            'echo "Restarting services..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && sudo {self.bench_path} setup production ubuntu --yes) # For restarting services',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Setup Production", start_time, output, traceback)

    def download_backup(self):
        start_time = now()

        if not self.site.restored_from_backup:
            self.update_agent_job_step("Download Backup", start_time, skipped=True)
            return

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

        s3 = setup_s3_client()
        for file_url in backup_files:
            change_file_permissions(s3, file_url, "public-read")
        
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Download Backup", start_time, output, traceback)

        for file_url in backup_files:
            change_file_permissions(s3, file_url, "private")

    def create_site(self):
        start_time = now()
        admin_password = self.site.get_password("admin_password")

        if self.site.restored_from_backup:
            commands = [
                'echo "Creating site..."',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && gunzip -c {self.db_backup_path} > backup.sql)',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} new-site --db-name {self.db_name} --mariadb-root-username {self.db_user} --mariadb-root-password {self.db_root_password} --admin-password {admin_password} --source_sql {self.frappe_bench_dir}/backup.sql {self.server_abbr} --force)',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} set-admin-password {admin_password})',
                'echo "Installing apps..."',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} install-app erpnext)',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} install-app bizkit_core)',
                'echo "Running patches and build..."',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} update --patch --build --no-backup)'
            ]
        else:
            commands = [
                'echo "Creating site..."',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} new-site --db-name {self.db_name} --mariadb-root-username {self.db_user} --mariadb-root-password {self.db_root_password} --admin-password {admin_password} {self.server_abbr} --force)',
                'echo "Installing apps..."',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} install-app erpnext --run-patches)',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} --site {self.server_abbr} install-app bizkit_core --run-patches)',
                'echo "Running patches and build..."',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} migrate --skip-failing) # Workaround: migrate and skip failing patches before running update to build prereqs first',
                f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} update --patch --build --no-backup)'
            ]

        if self.environment == "Production":
            commands.append(f'source ~/.profile && (cd {self.frappe_bench_dir} && sudo {self.bench_path} setup production ubuntu --yes)')

        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Create Site", start_time, output, traceback)

    def restore_files(self):
        start_time = now()
        
        if not self.site.restored_from_backup:
            self.update_agent_job_step("Restore Files", start_time, skipped=True)
            return
        
        commands = [
            'echo "Restoring files..."',
        ]

        if self.public_path:
            commands.append(f'''source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} execute frappe.installer.extract_files --args "'{self.server_abbr}','{self.public_path}'")''')
        
        if self.private_path:
            commands.append(f'''source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} execute frappe.installer.extract_files --args "'{self.server_abbr}','{self.private_path}'")''')

        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Restore Files", start_time, output, traceback)

    def install_additional_apps(self):
        start_time = now()
        
        press_settings = frappe.get_single("Press Settings")
        default_apps = press_settings.get_default_apps() or DEFAULT_APPS
        site_apps = frappe.get_all("Site App", filters={"parent": self.site.name}, pluck="app")
        apps = list(set(site_apps) - set(default_apps))
        if not apps:
            self.update_agent_job_step("Install Additional Apps", start_time, skipped=True)
            return
        
        commands = ['echo "Installing additional apps..."']

        main_command = 'source ~/.profile && (cd {frappe_bench_dir} && {command})'
        for app in apps:
            repo_url, branch = frappe.db.get_value("App Source", {"app": app, "enabled": 1}, ["ssh_url", "branch"])
            prereq_script = frappe.db.get_value("App", app, "installation_script_bash")
            if prereq_script:
                prereq_script_command = f"source ~/.profile && bash <<EOF\n{prereq_script}\nEOF"
                commands.append(prereq_script_command)

            get_app_command = f"{self.bench_path} get-app {repo_url} --branch {branch}"
            install_command = f"{self.bench_path} --site {self.server_abbr} install-app {app}"

            formatted_get_app_command = main_command.format(frappe_bench_dir=self.frappe_bench_dir, command=get_app_command)
            formatted_install_command = main_command.format(frappe_bench_dir=self.frappe_bench_dir, command=install_command)

            commands.append(formatted_get_app_command)
            commands.append(formatted_install_command)
        
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Install Additional Apps", start_time, output, traceback)

    def set_developer_mode(self):
        start_time = now()
        
        if self.environment == "Production":
            self.update_agent_job_step("Set Developer Mode", start_time, skipped=True)
            return
        
        commands = [
            'echo "Setting site to developer mode..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} set-config -g developer_mode 1)',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {self.bench_path} clear-cache)',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Set Developer Mode", start_time, output, traceback)

    def restart_bench(self):
        start_time = now()
        
        if self.environment == "Production":
            self.update_agent_job_step("Restart Bench", start_time, skipped=True)
            return
        
        commands = [
            'echo "Restarting bench..."',
            'source ~/.profile && sudo systemctl restart bench-start.service',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Restart Bench", start_time, output, traceback)

    def remove_fail2ban(self):
        start_time = now()
        
        if self.environment != "Production":
            self.update_agent_job_step("Remove Fail2Ban", start_time, skipped=True)
            return
        
        commands = [
            'echo "Removing fail2ban..."',
            'source ~/.profile && sudo systemctl stop fail2ban',
            'source ~/.profile && sudo apt-get remove --auto-remove fail2ban --yes',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Remove Fail2Ban", start_time, output, traceback)

    def run_initial_setup(self):
        start_time = now()

        if self.site.restored_from_backup:
            self.update_agent_job_step("Run Initial Setup", start_time, skipped=True)
            return

        hris_config = ""
        answer_no = "yes n | "
        if "HRIS" in self.site.product:
            hris_config = "--include-hris-config"
            answer_no = ""
        commands = [
            'echo "Running initial setup..."',
            f'source ~/.profile && (cd {self.frappe_bench_dir} && {answer_no}{self.bench_path} run-initial-setup --company-name "{self.site.company_name}" --company-abbreviation "{self.site.company_name_abbreviation}" --mariadb-root-login {self.db_user} --mariadb-root-password {self.db_root_password} --keep-active-domains --force-create-db {hris_config})',
        ]
        output, traceback = self.execute_commands(commands)
        self.update_agent_job_step("Run Initial Setup", start_time, output, traceback)


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
