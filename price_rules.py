"""Regras puras para validade da revisão de preços."""

from datetime import date, datetime, timedelta


SUPPORTED_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y")


def parse_review_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value or "").strip()
    if not text:
        return None

    for date_format in SUPPORTED_DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def is_price_outdated(value, today=None, max_age_days=90):
    review_date = parse_review_date(value)
    if review_date is None:
        return True
    reference_date = today or date.today()
    return reference_date > review_date + timedelta(days=max_age_days)
