from frappe.model.document import Document


class SiteSchedulePreset(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		preset_name: DF.Data
		monday: DF.Check
		tuesday: DF.Check
		wednesday: DF.Check
		thursday: DF.Check
		friday: DF.Check
		saturday: DF.Check
		sunday: DF.Check
		all_day: DF.Check
		start_time: DF.Time | None
		stop_time: DF.Time | None
	# end: auto-generated types

	dashboard_fields = (
		"preset_name",
		"monday",
		"tuesday",
		"wednesday",
		"thursday",
		"friday",
		"saturday",
		"sunday",
		"all_day",
		"start_time",
		"stop_time",
	)
