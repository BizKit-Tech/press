# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

import re
import typing
from textwrap import dedent
from typing import Callable, Optional, TypedDict

import frappe
import frappe.utils

"""
Used to create notifications if the Deploy error is something that can
be handled by the user.

Ref: https://github.com/frappe/press/pull/1544

To handle an error:
1. Create a doc page that helps the user get out of it under: frappecloud.com/docs/common-issues
2. Check if the error is the known/expected one in `get_details`.
3. Update the details object with the correct values.
"""

Details = TypedDict(
	"Details",
	{
		"title": Optional[str],
		"message": str,
		"traceback": Optional[str],
		"is_actionable": bool,
		"assistance_url": Optional[str],
	},
)

# These strings are checked against the traceback or build_output
MatchStrings = str | list[str]

if typing.TYPE_CHECKING:
	from frappe import Document
	from press.press.doctype.deploy_candidate.deploy_candidate import DeployCandidate

	# TYPE_CHECKING guard for code below cause DeployCandidate
	# might cause circular import.
	UserAddressableHandler = Callable[
		[
			Details,
			DeployCandidate,
			BaseException,
		],
		bool,  # Return True if is_actionable
	]
	UserAddressableHandlerTuple = tuple[
		MatchStrings,
		UserAddressableHandler,
	]


DOC_URLS = {
	"app-installation-issue": "https://frappecloud.com/docs/faq/app-installation-issue",
	"invalid-pyproject-file": "https://frappecloud.com/docs/common-issues/invalid-pyprojecttoml-file",
	"incompatible-node-version": "https://frappecloud.com/docs/common-issues/incompatible-node-version",
	"incompatible-dependency-version": "https://frappecloud.com/docs/common-issues/incompatible-dependency-version",
	"incompatible-app-version": "https://frappecloud.com/docs/common-issues/incompatible-app-version",
	"required-app-not-found": "https://frappecloud.com/docs/common-issues/required-app-not-found",
	"debugging-app-installs-locally": "https://frappecloud.com/docs/common-issues/debugging-app-installs-locally",
	"vite-not-found": "https://frappecloud.com/docs/common-issues/vite-not-found",
}


def handlers() -> "list[UserAddressableHandlerTuple]":
	"""
	Before adding anything here, view the type:
	`UserAddressableHandlerTuple`

	The first value of the tuple is `MatchStrings` which
	a list of strings (or a single string) which if they
	are present in the `traceback` or the `build_output`
	then then second value i.e. `UserAddressableHandler`
	is called.

	`UserAddressableHandler` is used to update the details
	used to create the Press Notification

	`UserAddressableHandler` can return False if it isn't
	user addressable, in this case the remaining handler
	tuple will be checked.

	Due to this order of the tuples matter.
	"""
	return [
		(
			"App installation token could not be fetched",
			update_with_installation_token_not_fetchable,
		),
		(
			"Repository could not be fetched",
			update_with_repository_not_fetchable,
		),
		(
			"App has invalid pyproject.toml file",
			update_with_invalid_pyproject_error,
		),
		(
			"App has invalid package.json file",
			update_with_invalid_package_json_error,
		),
		(
			'engine "node" is incompatible with this module',
			update_with_incompatible_node,
		),
		(
			"Incompatible Node version found",
			update_with_incompatible_app_prebuild,
		),
		(
			"Incompatible Python version found",
			update_with_incompatible_python_prebuild,
		),
		(
			"Incompatible app version found",
			update_with_incompatible_app_prebuild,
		),
		(
			"Invalid release found",
			update_with_invalid_release_prebuild,
		),
		(
			"Required app not found",
			update_with_required_app_not_found_prebuild,
		),
		(
			"note: This error originates from a subprocess, and is likely not a problem with pip.",
			update_with_error_on_pip_install,
		),
		(
			"ModuleNotFoundError: No module named",
			update_with_module_not_found,
		),
		(
			"ImportError: cannot import name",
			update_with_import_error,
		),
		(
			"No matching distribution found for",
			update_with_dependency_not_found,
		),
		(
			"[ERROR] [plugin vue]",
			update_with_vue_build_failed,
		),
		(
			"[ERROR] [plugin frappe-vue-style]",
			update_with_vue_build_failed,
		),
		(
			"vite: not found",
			update_with_vite_not_found,
		),
	]


def create_build_failed_notification(
	dc: "DeployCandidate", exc: "BaseException"
) -> bool:
	"""
	Used to create press notifications on Build failures. If the notification
	is actionable then it will be displayed on the dashboard and will block
	further builds until the user has resolved it.

	Returns True if build failure is_actionable
	"""

	details = get_details(dc, exc)
	doc_dict = {
		"doctype": "Press Notification",
		"team": dc.team,
		"type": "Bench Deploy",
		"document_type": dc.doctype,
		"document_name": dc.name,
		"class": "Error",
		**details,
	}
	doc = frappe.get_doc(doc_dict)
	doc.insert()
	frappe.db.commit()

	frappe.publish_realtime(
		"press_notification", doctype="Press Notification", message={"team": dc.team}
	)

	return details["is_actionable"]


def get_details(dc: "DeployCandidate", exc: BaseException) -> "Details":
	tb = frappe.get_traceback(with_context=False)
	default_title = get_default_title(dc)
	default_message = (get_default_message(dc),)

	details: "Details" = dict(
		title=default_title,
		message=default_message,
		traceback=tb,
		is_actionable=False,
		assistance_url=None,
	)

	for strs, handler in handlers():
		if isinstance(strs, str):
			strs = [strs]

		if not (is_match := all(s in tb for s in strs)):
			is_match = all(s in dc.build_output for s in strs)

		if not is_match:
			continue

		if handler(details, dc, exc):
			details["is_actionable"] = True
			break
		else:
			details["title"] = default_title
			details["message"] = default_message
			details["traceback"] = tb
			details["is_actionable"] = False
			details["assistance_url"] = None

	return details


def update_with_vue_build_failed(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):

	failed_step = get_failed_step(dc)
	app_name = None

	details["title"] = "App installation failed due to errors in frontend code"

	if failed_step.stage_slug == "apps":
		app_name = failed_step.step
		message = f"""
		<p><b>{app_name}</b> installation has failed due to errors in its
		frontend (Vue.js) code.</p>

		<p>Please view the failing step <b>{failed_step.stage} - {failed_step.step}</b>
		output to debug and fix the error before retrying build.</p>
		"""
	else:
		message = """
		<p>App installation has failed due to errors in its frontend (Vue.js) code.</p>

		<p>Please view the build output to debug and fix the error before retrying
		build.</p>
		"""

	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["debugging-app-installs-locally"]
	return True


def update_with_import_error(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):

	failed_step = get_failed_step(dc)
	app_name = None

	details["title"] = "App installation failed due to invalid import"

	lines = [
		line
		for line in dc.build_output.split("\n")
		if "ImportError: cannot import name" in line
	]
	invalid_import = None
	if len(lines) > 1 and len(parts := lines[0].split("From")) > 1:
		imported = parts[0].strip().split(" ")[-1][1:-1]
		module = parts[1].strip().split(" ")[0][1:-1]
		invalid_import = f"{imported} from {module}"

	if failed_step.stage_slug == "apps" and invalid_import:
		app_name = failed_step.step
		message = f"""
		<p><b>{app_name}</b> installation has failed due to invalid import
		<b>{invalid_import}</b>.</p>

		<p>Please ensure all Python dependencies are of the required
		versions.</p>

		<p>Please view the failing step <b>{failed_step.stage} - {failed_step.step}</b>
		output to debug and fix the error before retrying build.</p>
		"""
	else:
		message = """
		<p>App installation failed due to an invalid import.</p>

		<p>Please view the build output to debug and fix the error
		before retrying build.</p>
		"""

	details["assistance_url"] = DOC_URLS["debugging-app-installs-locally"]
	details["message"] = fmt(message)
	return True


def update_with_module_not_found(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):

	failed_step = get_failed_step(dc)
	app_name = None

	details["title"] = "App installation failed due to missing module"

	lines = [
		line
		for line in dc.build_output.split("\n")
		if "ModuleNotFoundError: No module named" in line
	]
	missing_module = None
	if len(lines) > 1:
		missing_module = lines[0].split(" ")[-1][1:-1]

	if failed_step.stage_slug == "apps" and missing_module:
		app_name = failed_step.step
		message = f"""
		<p><b>{app_name}</b> installation has failed due to imported module
		<b>{missing_module}</b> not being found.</p>

		<p>Please ensure all imported Frappe app dependencies have been added
		to your bench and all Python dependencies have been added to your app's
		<b>requirements.txt</b> or <b>pyproject.toml</b> file before retrying
		the build.</p>
		"""
	else:
		message = """
		<p>App installation failed due to an imported module not being found.</p>

		<p>Please view the failing step output to debug and fix the error
		before retrying build.</p>
		"""

	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["debugging-app-installs-locally"]
	return True


def update_with_dependency_not_found(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):

	failed_step = get_failed_step(dc)
	app_name = None

	details["title"] = "App installation failed due to dependency not being found"

	lines = [
		line
		for line in dc.build_output.split("\n")
		if "No matching distribution found for" in line
	]
	missing_dep = None
	if len(lines) > 1:
		missing_dep = lines[0].split(" ")[-1]

	if failed_step.stage_slug == "apps" and missing_dep:
		app_name = failed_step.step
		message = f"""
		<p><b>{app_name}</b> installation has failed due to dependency
		<b>{missing_dep}</b> not being found.</p>

		<p>Please specify a version of <b>{missing_dep}</b> installable by
		<b>pip</b>.</p>

		<p>Please view the failing step output for more info.</p>
		"""
	else:
		message = """
		<p>App installation failed due to pip not being able to find a
		distribution of a dependency in your app.</p>

		<p>Please view the build output to debug and fix the error before
		retrying build.</p>
		"""

	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["debugging-app-installs-locally"]
	return True


def update_with_error_on_pip_install(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):

	failed_step = get_failed_step(dc)
	app_name = None

	details["title"] = "App installation failed due to errors"

	if failed_step.stage_slug == "apps":
		app_name = failed_step.step
		message = f"""
		<p>Dependency installation using pip for <b>{app_name}</b> failed due to
		errors originating in the app.</p>

		<p>Please view the failing step <b>{failed_step.stage} - {failed_step.step}</b>
		output to debug and fix the error before retrying build.</p>
		"""
	else:
		message = """
		<p>Dependency installation using pip failed due to errors originating in an
		app on your Bench.</p>

		<p>Please view the build output to debug and fix the error before retrying
		build.</p>
		"""

	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["debugging-app-installs-locally"]
	return True


def update_with_invalid_pyproject_error(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):
	if len(exc.args) <= 1 or not (app := exc.args[1]):
		return False

	build_step = get_ct_row(dc, app, "build_steps", "step_slug")
	app_name = build_step.step

	details["title"] = "Invalid pyproject.toml file found"
	message = f"""
	<p>The <b>pyproject.toml</b> file in the <b>{app_name}</b> repository could not be
	decoded by <code>tomllib</code> due to syntax errors.</p>

	<p>To rectify this issue, please follow the steps mentioned in <i>Help</i>.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["invalid-pyproject-file"]
	return True


def update_with_invalid_package_json_error(
	details: "Details",
	dc: "DeployCandidate",
	exc: "BaseException",
):
	if len(exc.args) <= 1 or not (app := exc.args[1]):
		return False

	build_step = get_ct_row(dc, app, "build_steps", "step_slug")
	app_name = build_step.step

	loc_str = ""
	if len(exc.args) >= 2 and isinstance(exc.args[2], str):
		loc_str = f"<p>File was found at path <b>{exc.args[2]}</b>.</p>"

	details["title"] = "Invalid package.json file found"
	message = f"""
	<p>The <b>package.json</b> file in the <b>{app_name}</b> repository could not be
	decoded by <code>json.load</code>.</p>
	{loc_str}

	<p>To rectify this issue, please fix the <b>pyproject.json</b> file.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["debugging-app-installs-locally"]
	return True


def update_with_installation_token_not_fetchable(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
):
	return _update_with_github_token_error(details, dc, exc, False)


def update_with_repository_not_fetchable(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
):
	return _update_with_github_token_error(details, dc, exc, True)


def _update_with_github_token_error(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
	is_repo_not_found: bool = False,
):
	if len(exc.args) > 1:
		app = exc.args[1]
	elif (failed_step := dc.get_first_step("status", "Failure")) is not None:
		app = failed_step.step_slug

	if not app:
		return False

	# Ensure that installation token is None
	if is_repo_not_found and not is_installation_token_none(dc, app):
		return False

	build_step = get_ct_row(dc, app, "build_steps", "step_slug")
	if not build_step:
		return False

	details["title"] = "App access token could not be fetched"

	app_name = build_step.step
	message = f"""
	<p>{details['message']}</p>

	<p><b>{app_name}</b> installation access token could not be fetched from GitHub.
	To rectify this issue, please follow the steps mentioned in <i>Help</i>.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["app-installation-issue"]
	return True


def update_with_incompatible_node(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
) -> None:
	# Example line:
	# `#60 5.030 error customization_forms@1.0.0: The engine "node" is incompatible with this module. Expected version ">=18.0.0". Got "16.16.0"`
	line = get_build_output_line(dc, '"node" is incompatible with this module')
	app = get_app_from_incompatible_build_output_line(line)
	version = get_version_from_incompatible_build_output_line(line)

	details["title"] = "Incompatible Node version"
	message = f"""
	<p>{details['message']}</p>

	<p><b>{app}</b> installation failed due to incompatible Node versions. {version}
	Please set the correct Node Version on your Bench.</p>

	<p>To rectify this issue, please follow the the steps mentioned in <i>Help</i>.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["incompatible-node-version"]

	# Traceback is not pertinent to issue
	details["traceback"] = None
	return True


def update_with_incompatible_node_prebuild(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
) -> None:
	if len(exc.args) != 5:
		return False

	_, app, actual, expected, package_name = exc.args

	package_name_str = ""
	if isinstance(package_name, str):
		package_name_str = f"Version requirement comes from package <b>{package_name}</b>"

	details["title"] = "Validation Failed: Incompatible Node version"
	message = f"""
	<p><b>{app}</b> requires Node version <b>{expected}</b>, found version is <b>{actual}</b>.
	{package_name_str}

	Please set the correct Node version on your Bench.</p>

	<p>To rectify this issue, please follow the the steps mentioned in <i>Help</i>.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["incompatible-node-version"]

	# Traceback is not pertinent to issue
	details["traceback"] = None
	return True


def update_with_incompatible_python_prebuild(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
) -> None:
	if len(exc.args) != 4:
		return False

	_, app, actual, expected = exc.args

	details["title"] = "Validation Failed: Incompatible Python version"
	message = f"""
	<p><b>{app}</b> requires Python version <b>{expected}</b>, found version is <b>{actual}</b>.
	Please set the correct Python version on your Bench.</p>

	<p>To rectify this issue, please follow the the steps mentioned in <i>Help</i>.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["incompatible-dependency-version"]

	# Traceback is not pertinent to issue
	details["traceback"] = None
	return True


def update_with_incompatible_app_prebuild(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
) -> None:
	if len(exc.args) != 5:
		return False

	_, app, dep_app, actual, expected = exc.args

	details["title"] = "Validation Failed: Incompatible app version"

	message = f"""
	<p><b>{app}</b> depends on version <b>{expected}</b> of <b>{dep_app}</b>.
	Found version is <b>{actual}</b></p>

	<p>To fix this issue please set <b>{dep_app}</b> to version <b>{expected}</b>.</p>
	"""
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["incompatible-app-version"]

	# Traceback is not pertinent to issue
	details["traceback"] = None
	return True


def update_with_invalid_release_prebuild(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
):
	if len(exc.args) != 4:
		return False

	_, app, hash, invalidation_reason = exc.args

	details["title"] = "Validation Failed: Invalid app release"
	message = f"""
	<p>App <b>{app}</b> has an invalid release with the commit hash
	<b>{hash[:10]}</b></p>

	<p>To rectify this, please fix the issue mentioned below and
	push a new update.</p>
	"""
	details["traceback"] = invalidation_reason
	details["message"] = fmt(message)
	return True


def update_with_required_app_not_found_prebuild(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
):
	if len(exc.args) != 3:
		return False

	_, app, required_app = exc.args

	details["title"] = "Validation Failed: Required app not found"
	message = f"""
	<p><b>{app}</b> has a dependency on the app <b>{required_app}</b>
	which was not found on your bench.</p>

	<p>To rectify this issue, please add the required app to your Bench
	and try again.</p>
	"""
	details["traceback"] = None
	details["message"] = fmt(message)
	details["assistance_url"] = DOC_URLS["required-app-not-found"]
	return True


def update_with_vite_not_found(
	details: "Details",
	dc: "DeployCandidate",
	exc: BaseException,
):
	details["title"] = "Vite not found"
	failed_step = get_failed_step(dc)
	if failed_step.stage_slug == "apps":
		app_name = failed_step.step
		message = f"""
		<p><b>{app_name}</b> installation has failed due the build
		dependency Vite not being found.</p>

		<p>To rectify this issue, please follow the steps mentioned
		in <i>Help</i>.</p>
		"""
	else:
		message = """
		<p>App installation has failed due the build dependency Vite
		not being found.</p>

		<p>To rectify this issue, please follow the steps mentioned
		in <i>Help</i>.</p>
		"""

	details["message"] = fmt(message)
	details["traceback"] = None
	details["assistance_url"] = DOC_URLS["vite-not-found"]
	return True


def fmt(message: str) -> str:
	message = message.strip()
	message = dedent(message)
	return re.sub(r"\s+", " ", message)


def get_build_output_line(dc: "DeployCandidate", needle: str):
	for line in dc.build_output.split("\n"):
		if needle in line:
			return line
	return ""


def get_version_from_incompatible_build_output_line(line: str):
	if "Expected" not in line:
		return ""

	idx = line.index("Expected")
	return line[idx:] + "."


def get_app_from_incompatible_build_output_line(line: str):
	splits = line.split()
	if "error" not in splits:
		return ""

	idx = splits.index("error") + 1
	if len(splits) <= idx:
		return ""

	return splits[idx][:-1].split("@")[0]


def is_installation_token_none(dc: "DeployCandidate", app: str) -> bool:
	from press.api.github import get_access_token

	dc_app = get_ct_row(dc, app, "apps", "app")
	if dc_app is None:
		return False

	installation_id = frappe.get_value(
		"App Source", dc_app.source, "github_installation_id"
	)

	try:
		return get_access_token(installation_id) is None
	except Exception:
		# Error is not actionable
		return False


def get_default_title(dc: "DeployCandidate") -> str:
	return "Build Failed"


def get_default_message(dc: "DeployCandidate") -> str:
	failed_step = dc.get_first_step("status", "Failure")
	if failed_step:
		return f"Image build failed at step <b>{failed_step.stage} - {failed_step.step}</b>."
	return "Image build failed."


def get_is_actionable(dc: "DeployCandidate", tb: str) -> bool:
	return False


def get_ct_row(
	dc: "DeployCandidate",
	match_value: str,
	field: str,
	ct_field: str,
) -> Optional["Document"]:
	ct = dc.get(field)
	if not ct:
		return

	for row in ct:
		if row.get(ct_field) == match_value:
			return row


def get_failed_step(dc: "DeployCandidate"):
	return dc.get_first_step("status", "Failure") or frappe._dict()
