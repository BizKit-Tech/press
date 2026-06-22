from frappe.model.document import Document


class SiteSchedule(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		site: DF.Link
		enabled: DF.Check
		preset: DF.Link
		override: DF.Literal["None", "Until Datetime", "Indefinite"]
		override_until: DF.Datetime | None
	# end: auto-generated types

