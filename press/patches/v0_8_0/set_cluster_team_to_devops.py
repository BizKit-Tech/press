import frappe


def execute():
	team = frappe.db.get_value("Team", {"team_title": "DevOps"}, "name")
	if not team:
		return

	clusters = frappe.get_all("Cluster", filters={"team": ("is", "not set")}, pluck="name")
	for cluster in clusters:
		frappe.db.set_value("Cluster", cluster, "team", team)
