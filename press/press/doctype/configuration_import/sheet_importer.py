import os
import frappe
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from abc import ABC, abstractmethod
from gspread.exceptions import WorksheetNotFound
from json.decoder import JSONDecodeError


JSON_KEYFILE = os.path.abspath(frappe.get_site_path("google_keyfile.json"))
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
SETTINGS_LIST = [
    "Accounts Settings",
    "Buying Settings",
    "Selling Settings",
    "Stock Settings",
    "System Settings",
    "Item Price Settings",
]
WORKSHEETS = [
    "New Fields",
    "Field Properties",
    "Roles and Permissions",
    *SETTINGS_LIST,
]


class JSONKeyFileError(Exception):
    pass


class SheetImporter(ABC):
    @abstractmethod
    def get_worksheet(self, sheet_name):
        pass

    @abstractmethod
    def get_worksheet_data(self, sheet_name, as_list=False):
        pass


class GoogleSheetImporter(SheetImporter):
    def __init__(self, workbook_url):
        self.initialize_client()
        self.set_workbook(workbook_url)

    def initialize_client(self):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                JSON_KEYFILE, SCOPES
            )
        except JSONDecodeError:
            raise JSONKeyFileError(
                "Please ensure that the Google API credentials have been correctly pasted in the file google_keyfile.json and are in a valid JSON format."
            )
        else:
            self.client = gspread.authorize(creds)

    def set_workbook(self, workbook_url):
        if workbook_url.startswith("https://docs.google.com/spreadsheets"):
            self.workbook = self.client.open_by_url(workbook_url)
        else:
            raise ValueError("URL must be a Google Sheet URL")

    def get_worksheet(self, sheet_name):
        try:
            worksheet = self.workbook.worksheet(sheet_name)
        except WorksheetNotFound:
            error_msg = "Worksheet name must be one of the following: " + ", ".join(
                WORKSHEETS
            )
            raise ValueError(error_msg)
        else:
            return worksheet

    def get_worksheet_data(self, sheet_name, as_list=False):
        """
        Returns a list of dictionaries by default. Each dictionary represents a row in the sheet.
        If as_list is True, returns a list of lists.
        """
        worksheet = self.get_worksheet(sheet_name)
        if as_list:
            data = worksheet.get_values()
        else:
            data = worksheet.get_all_records()

        return data


def get_sheet_importer(sheet_type, sheet_location):
    sheet_type = sheet_type.lower()
    if sheet_type == "google":
        return GoogleSheetImporter(sheet_location)
    elif sheet_type == "excel":
        return
