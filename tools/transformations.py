"""Conservative, deterministic transformations: retain invalid values for review."""
import re
from datetime import datetime
import pandas as pd
from models.migration import FieldRule
from tools.profiling import missing


def normalize_text(value):
    return None if missing(value) else ' '.join(str(value).strip().split())


def normalize_email(value):
    value = normalize_text(value)
    return value.lower() if value is not None else None


def normalize_phone(value):
    if missing(value):
        return None
    original = str(value).strip()
    # Letters/extensions are uncertain; do not silently strip them.
    if re.search(r'[^\d\s()+.\-]', original):
        return original
    digits = re.sub(r'\D', '', original)
    if original.startswith('00'):
        return '+' + digits[2:]
    return ('+' if original.startswith('+') else '') + digits


def normalize_date(value, date_order=None):
    if missing(value):
        return None
    original = str(value).strip()
    formats = ['%Y-%m-%d', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S', '%d %b %Y', '%d %B %Y']
    match = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', original)
    if match:
        first, second = int(match[1]), int(match[2])
        if first <= 12 and second <= 12 and first != second and date_order is None:
            return original  # Cannot infer locale safely.
        order = date_order or ('dayfirst' if first > 12 else 'monthfirst')
        formats += ['%d/%m/%Y', '%d-%m-%Y'] if order == 'dayfirst' else ['%m/%d/%Y', '%m-%d-%Y']
    for fmt in formats:
        try:
            return datetime.strptime(original, fmt).date().isoformat()
        except ValueError:
            continue
    return original


def convert_data_type(value, kind):
    if missing(value):
        return None
    original = str(value).strip()
    if kind == 'boolean':
        return {'true': 'true', 'false': 'false', '1': 'true', '0': 'false',
                'yes': 'true', 'no': 'false'}.get(original.lower(), original)
    try:
        from decimal import Decimal, InvalidOperation
        number = Decimal(original)
        if not number.is_finite() or (kind == 'integer' and number != number.to_integral_value()):
            return original
        return str(int(number)) if kind == 'integer' else format(number, 'f')
    except (InvalidOperation, ValueError):
        return original


def standardize_categories(value, rule: FieldRule):
    value = normalize_text(value)
    if value is None:
        return None
    mappings = {k.casefold(): v for k, v in rule.category_map.items()}
    mappings.update({k.casefold(): k for k in rule.allowed})
    return mappings.get(value.casefold(), value)


def handle_missing_values(series: pd.Series, rule: FieldRule) -> pd.Series:
    # Only schema-declared defaults, explicitly included in the approved plan.
    return series.map(lambda value: rule.default if missing(value) else value)


TRANSFORMERS = {
    'normalize_text': lambda value, rule: normalize_text(value),
    'normalize_email': lambda value, rule: normalize_email(value),
    'normalize_phone': lambda value, rule: normalize_phone(value),
    'normalize_date': lambda value, rule: normalize_date(value, rule.date_order),
    'convert_data_type': lambda value, rule: convert_data_type(value, rule.kind),
    'standardize_categories': standardize_categories,
}
