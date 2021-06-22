from openpyxl import load_workbook
import openpyxl.cell
from openpyxl.utils.cell import column_index_from_string
import datetime
from event import Event
import requests
from creds import DOWNLOAD_URL

class ExcelWorker:
    GRADES = {9: ('I', 'K'), 10: ('O', 'Q'), 11: ('U', 'W'), 13: ('Z', 'AB')}
    BAGROT_COLOR = 'FF0000FF'
    INSIDE_BAGROT_COLOR = 'FF3D85C6'
    DATE_COLUMN = 'F'

    def __init__(self, workbook_path: str):
        self.workbook_path = workbook_path
        self.workbook = load_workbook(self.workbook_path, read_only=True)
        self.worksheet = self.workbook.active
        self.schedule: dict[int, list[list[Event]]] = dict()
        self.update_schedule([0, 7, 14])
        self.expire_date: datetime.date = datetime.date.today()

    def open_worksheet(self):
        self.workbook = load_workbook(self.workbook_path, read_only=True)
        self.worksheet = self.workbook.active

    def get_this_week_row(self):
        today = datetime.date.today()
        sunday = today - datetime.timedelta(today.weekday() + 1)
        for cells in self.worksheet.iter_rows(max_col=column_index_from_string(self.DATE_COLUMN),
                                              min_col=column_index_from_string(self.DATE_COLUMN),
                                              min_row=3):
            cell: openpyxl.cell.cell.Cell = cells[0]
            if sunday == cell.value.date():
                return cell.row

    def parse_today_events(self, row: tuple) -> list:
        events = []
        for event in row:
            if event and event.value and event not in events:
                events.append(event)
        return events

    def get_week_events(self, starting_col, grade) -> list[Event]:
        events: list[Event] = []
        for cells in self.worksheet.iter_rows(min_row=starting_col, max_row=starting_col + 5,
                                              min_col=column_index_from_string(self.GRADES[grade][0]),
                                              max_col=column_index_from_string(self.GRADES[grade][1])):

            for cell in self.parse_today_events(cells):
                if not cell.value:  # cell is empty
                    continue
                date = self.worksheet[f'{self.DATE_COLUMN}{cell.row}'].value.date()
                if cell.value.startswith('מתכ.'):
                    events.append(Event(cell.value[4:].strip(" "), "מתכונת", date))
                elif cell.fill.start_color.index == self.BAGROT_COLOR:
                    events.append(Event(cell.value.strip(" "), "בגרות", date))
                elif cell.fill.start_color.index == self.INSIDE_BAGROT_COLOR:
                    events.append(Event(cell.value.strip(" "), "בגרות פנימית", date))
                else:
                    events.append(Event(cell.value.strip(" "), "", date))

        return events

    def update_schedule(self, intervals: list[int]):
        # get the most up-to-date version of the excel
        self.workbook.close()
        file = requests.get(DOWNLOAD_URL)

        with open(self.workbook_path, 'wb') as excel_file:
            excel_file.write(file.content)

        self.open_worksheet()   # refresh the worksheet

        row = self.get_this_week_row() + 7  # start from next week
        for grade in self.GRADES:
            self.schedule[grade] = []
        for grade in self.GRADES:
            for week_interval in intervals:
                self.schedule[grade].append(self.get_week_events(row + week_interval, grade))

        self.expire_date = datetime.date.today() + datetime.timedelta(days=intervals[-1])

    def get_schedule(self, intervals: list[int]) -> dict[int, list[list[Event]]]:
        # before updating check if schedule's last date
        # hasn't expired
        if self.expire_date >= datetime.date.today():
            return self.schedule
        self.update_schedule(intervals)
        return self.schedule
