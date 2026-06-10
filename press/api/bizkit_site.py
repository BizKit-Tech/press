import frappe
import re


def slugify(s):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_-]+', '-', s)
    s = re.sub(r'^-+|-+$', '', s)
    return s


def unique_name(doctype, filters, base_name):
    if frappe.db.exists(doctype, filters):
        count = frappe.db.count(doctype, filters) + 1
        return base_name + str(count)
    return base_name


def assert_server_active(doc, label):
    doc.reload()
    if doc.status == "Broken":
        frappe.throw(f"{label} setup failed")


@frappe.whitelist()
def new(args):
    frappe.enqueue(_new, args=args, queue="long", timeout=3600)


def _new(args):
    cluster = args.get("cluster")
    project_name = args.get("project_name")
    company_name = args.get("company_name")
    company_name_abbr = args.get("company_name_abbr")
    environment = args.get("environment")
    apps = args.get("apps")
    product = args.get("product")
    tenancy = args.get("tenancy")
    site_plan = args.get("site_plan")
    backup = args.get("backup")

    team = frappe.db.get_value("Team", {"team_title": "DevOps"}, "name")
    site_plan_details = get_site_plan_details(site_plan)
    domain = frappe.db.get_value("Root Domain", {"environment": environment}, "name")
    is_new = cluster == "New Client"

    try:
        if is_new:
            print("Creating new client")
            print("Creating cluster")
            cluster = create_cluster(project_name)
            print("Creating database server")
            db_server = create_database_server(project_name, cluster, site_plan_details)
        else:
            cluster = project_name
            db_server = frappe.db.get_value("Database Server", {"cluster": cluster, "is_server_setup": 1}, "name")

        print("Creating app server")
        app_server = create_app_server(project_name, cluster, environment, site_plan_details, db_server, domain)

        if release_group := get_existing_release_group(apps):
            print("Adding server to existing release group")
        else:
            print("Creating new release group")
            release_group = create_release_group(project_name, apps, team)
            print("Creating deploy candidate")
            create_deploy_candidate(release_group)

        print("Adding server to release group and creating bench")
        bench = add_server_to_release_group(release_group, app_server)

        print("Creating site")
        site = create_site(company_name, company_name_abbr, bench, product, tenancy, release_group, cluster, app_server, project_name, team, domain, site_plan, backup)

        create_notification({
            "team": team,
            "doctype": "Site",
            "docname": site.name,
            "title": "Site Configuration in Progress",
            "message": "Your servers are ready and the site creation is now underway. You can track the progress in the logs here: " + frappe.utils.get_url(f"/dashboard/sites/{site}/insights/jobs"),
            "traceback": None,
        })

    except Exception as e:
        if is_new:
            cluster = project_name

        create_notification({
            "team": team,
            "doctype": "Cluster",
            "docname": cluster,
            "title": "Site Creation Failed",
            "message": "An error occurred while creating the site. Please see the traceback for more details.",
            "traceback": str(e),
        })
        raise e


def get_site_plan_details(site_plan):
    doc = frappe.get_doc("Site Plan", site_plan)
    return {
        "db_instance_type": doc.db_instance_type,
        "db_storage_size": doc.max_database_usage / 1024,
        "app_instance_type": doc.instance_type,
        "app_volume_size": doc.max_storage_usage / 1024,
    }


def create_cluster(project_name):
    cluster_doc = frappe.get_doc({
        "doctype": "Cluster",
        "name": project_name,
        "title": project_name,
        "status": "Pending",
        "public": 1,
        "cloud_provider": "Generic",
        "region": "ap-southeast-1",
    })
    cluster_doc.insert()
    frappe.db.commit()
    cluster_doc.reload()
    cluster_doc.prepare_vpc()
    return cluster_doc.name


def create_database_server(project_name, cluster_name, plan):
    domain = frappe.db.get_value("Root Domain", {"environment": "Database"}, "name")

    database_doc = frappe.get_doc({
        "doctype": "Database Server",
        "hostname": slugify(project_name),
        "hostname_abbreviation": slugify(project_name),
        "domain": domain,
        "title": project_name,
        "provider": "AWS RDS",
        "cluster": cluster_name,
        "instance_type": plan["db_instance_type"],
        "storage_size": plan["db_storage_size"],
        "is_primary": 1,
        "ssh_user": "ubuntu",
        "ssh_port": 22,
        "backup_retention_period": 3,
        "backup_window_duration": 3600,
        "backup_window_start_time": "18:00:00",
        "maintenance_window_duration": 3600,
        "maintenance_window_start_day": "Sunday",
        "maintenance_window_start_time": "21:00:00",
    })
    database_doc.insert()
    frappe.db.commit()
    database_doc._setup_server()
    assert_server_active(database_doc, "Database Server")
    return database_doc.name


def create_app_server(project_name, cluster_name, environment, plan, database_server_name, domain):
    hostname = unique_name("Server", {"hostname": slugify(project_name), "domain": domain}, slugify(project_name))

    app_server_doc = frappe.get_doc({
        "doctype": "Server",
        "hostname": hostname,
        "hostname_abbreviation": hostname,
        "domain": domain,
        "title": project_name,
        "provider": "AWS EC2",
        "cluster": cluster_name,
        "environment": environment,
        "instance_type": plan["app_instance_type"],
        "volume_size": plan["app_volume_size"],
        "ssh_user": "ubuntu",
        "ssh_port": 22,
        "database_server": database_server_name,
    })
    app_server_doc.insert()
    frappe.db.commit()
    app_server_doc._setup_server()
    app_server_doc.connect_to_rds()
    assert_server_active(app_server_doc, "App Server")
    return app_server_doc.name


def create_release_group(project_name, apps, team):
    release_group_apps = []
    for app in apps:
        app_source = frappe.db.get_value("App Source", {"app": app, "enabled": 1}, "name")
        release_group_apps.append({"app": app, "source": app_source})

    release_group_doc = frappe.get_doc({
        "doctype": "Release Group",
        "title": project_name,
        "version": "Version 13",
        "team": team,
        "public": 1,
        "enabled": 1,
        "apps": release_group_apps,
    })
    release_group_doc.insert()
    frappe.db.commit()
    release_group_doc.reload()
    return release_group_doc.name


def add_server_to_release_group(release_group, app_server_name):
    release_group_doc = frappe.get_doc("Release Group", release_group)
    deploy = release_group_doc.add_server(app_server_name, True)
    bench = frappe.db.get_value("Deploy Bench", filters={"parent": deploy.name}, fieldname=["bench"])
    frappe.db.set_value("Bench", bench, "status", "Active")
    frappe.db.commit()
    return bench


def create_deploy_candidate(release_group):
    release_group_doc = frappe.get_doc("Release Group", release_group)
    deploy_candidate = release_group_doc.create_deploy_candidate()
    deploy_candidate.build()
    frappe.db.commit()
    return deploy_candidate.name


def create_site(company_name, company_name_abbr, bench_name, product, tenancy, release_group, cluster_name, app_server_name, project_name, team, domain, site_plan, backup):
    bench_doc = frappe.get_doc("Bench", bench_name)
    bench_apps = [{"app": app.app} for app in bench_doc.apps]

    server_doc = frappe.get_doc("Server", app_server_name)
    subdomain = unique_name("Site", {"subdomain": slugify(project_name), "domain": domain}, slugify(project_name))

    site_doc = frappe.get_doc({
        "doctype": "Site",
        "company_name": company_name,
        "company_name_abbreviation": company_name_abbr,
        "site_url": f"http://{server_doc.ip}",
        "bench": bench_name,
        "product": product,
        "tenancy": tenancy,
        "release_group": release_group,
        "cluster": cluster_name,
        "server": app_server_name,
        "subdomain": subdomain,
        "domain": domain,
        "team": team,
        "apps": bench_apps,
        "plan": site_plan,
        "restored_from_backup": backup,
    })
    site_doc.insert()
    frappe.db.commit()
    site_doc.reload()
    site_doc.install_site()
    return site_doc


def get_existing_release_group(apps):
    release_groups = frappe.get_all("Release Group", filters={"version": "Version 13", "public": 1, "enabled": 1})
    for release_group in release_groups:
        release_group_apps = frappe.get_all("Release Group App", filters={"parent": release_group.name}, fields=["app"])
        release_group_apps = [app.app for app in release_group_apps]
        if not list(set(apps) - set(release_group_apps)):
            return release_group.name


def create_notification(details):
    team = details.get("team")
    traceback = details.get("traceback")

    notification_doc = frappe.get_doc({
        "doctype": "Press Notification",
        "team": team,
        "type": "Site Update",
        "document_type": details.get("doctype"),
        "document_name": details.get("docname"),
        "class": "Error" if traceback else "Success",
        "title": details.get("title"),
        "message": details.get("message"),
        "traceback": traceback,
    })
    notification_doc.insert()
    frappe.db.commit()

    frappe.publish_realtime("press_notification", doctype="Press Notification", message={"team": team})
