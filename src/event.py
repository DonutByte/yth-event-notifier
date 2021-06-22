from dataclasses import dataclass
import datetime


@dataclass(frozen=True)
class Event:
    name: str
    date: datetime.date
