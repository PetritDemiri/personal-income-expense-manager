"""Ndihmesa per datat / Date helpers.

All date handling in the package goes through here, so the storage format is
defined in exactly one place.
"""

import calendar
import datetime

from .config import DATE_FORMAT, MONTH_FORMAT


def today():
    """Today's date. Wrapped in a function so tests can monkeypatch it."""
    return datetime.date.today()


def current_date_str():
    """Today's date as a dd-mm-yyyy string."""
    return format_date(today())


def parse_date(date_str):
    """Parse a dd-mm-yyyy string into a date, or return None if invalid."""
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(str(date_str).strip(), DATE_FORMAT).date()
    except (ValueError, TypeError):
        return None


def format_date(date_obj):
    """Format a date as a dd-mm-yyyy string."""
    return date_obj.strftime(DATE_FORMAT)


def parse_month(month_str):
    """Parse a mm-yyyy string into a (year, month) tuple, or None if invalid."""
    if not month_str:
        return None
    try:
        parsed = datetime.datetime.strptime(str(month_str).strip(), MONTH_FORMAT)
    except (ValueError, TypeError):
        return None
    return parsed.year, parsed.month


def format_month(year, month):
    """Format a (year, month) pair as mm-yyyy."""
    return f"{month:02d}-{year}"


def month_of(date_obj):
    """Return the (year, month) pair a date falls in."""
    return date_obj.year, date_obj.month


def month_bounds(year, month):
    """First and last dates of a month, as a (start, end) tuple."""
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)


def previous_month(year, month):
    """The (year, month) pair immediately before the given one."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def add_months(start_date, months):
    """Return start_date shifted forward by a number of months.

    The day is clamped to the last valid day of the target month, so a date
    anchored on the 31st lands on 28/29 February. Callers that generate a
    series should always count from the original start date rather than from
    the previous result, so clamping cannot make the day drift permanently.
    """
    month_index = start_date.month - 1 + months
    year = start_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)
