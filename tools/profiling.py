import re
import pandas as pd

EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PHONE = re.compile(r'^\+?[0-9]{7,15}$')


def missing(value) -> bool:
    return value is None or bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())


def inspect_schema(df: pd.DataFrame) -> dict[str, str]:
    return {str(column): str(dtype) for column, dtype in df.dtypes.items()}


def profile_data(df: pd.DataFrame) -> dict:
    columns = {}
    for name in df.columns:
        series = df[name]
        values = series[~series.map(missing)].astype(str)
        columns[name] = {
            'dtype': str(series.dtype), 'null_count': int(series.map(missing).sum()),
            'null_percent': round(float(series.map(missing).mean() * 100), 2),
            'unique_count': int(values.nunique()),
            'likely_identifier': bool(len(values) and values.nunique() == len(df)),
            'email_pattern_count': int(values.str.fullmatch(EMAIL).sum()),
            'phone_pattern_count': int(values.str.fullmatch(PHONE).sum()),
            'date_pattern_count': int(values.str.match(r'^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}').sum()),
            'categorical_candidate': bool(0 < values.nunique() <= min(20, max(2, len(df) // 5))),
            'whitespace_count': int((values != values.str.strip()).sum()),
        }
    return {'row_count': len(df), 'column_count': len(df.columns), 'columns': columns,
            'exact_duplicate_count': int(df.duplicated().sum())}
