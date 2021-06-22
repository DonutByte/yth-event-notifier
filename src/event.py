from dataclasses import dataclass
import datetime
from string import Template
import urllib.parse

TEMPLATE = Template(r"https://www.google.com/calendar/render?action=TEMPLATE&text=$title&dates=$date&details=%D7%94%D7"
                    r"%AA%D7%96%D7%9B%D7%95%D7%A8%D7%AA%20%D7%A0%D7%95%D7%A6%D7%A8%D7%94%20%D7%A2%22%D7%99%3Ahttps://t"
                    r".me/yth_robot&sf=true&output=xml")

@dataclass(frozen=True)
class Event:
    name: str
    type_: str
    date: datetime.date

    """
    uses: <name_format>|<date_format>
    """
    def google_event_gen(self):
        title = urllib.parse.quote((f'{self.type_} ב' if self.type_ != "" else "") + self.name)
        date = self.date.strftime('%Y%m%d')
        end_date = (self.date + datetime.timedelta(days=1)).strftime('%Y%m%d')
        url = TEMPLATE.substitute(title=title, date=f'{date}/{end_date}')
        return url

    def __format__(self, format_spec : str):
        name_format_spec, date_format_spec = format_spec.split('|')
        frmt = fr'[{format(self.date, date_format_spec)}]({self.google_event_gen()}) \-__{self.type_}__ {format(self.name, name_format_spec)}'
        return frmt
