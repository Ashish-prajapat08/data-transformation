import pandas as pd
from models.migration import TargetSchema
from tools.validation import validate_data


def export_data(df: pd.DataFrame, target: TargetSchema, pending_reviews: bool = False) -> bytes:
    if pending_reviews or not validate_data(df, target).passed:
        raise ValueError('Export requires successful validation and completed review')
    # Prevent spreadsheet formula execution while preserving ordinary phone prefixes.
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '@', '+', '-')):
            import re
            if not re.fullmatch(r'[+-]?\d+(\.\d+)?', value):
                return "'" + value
        return value
    return df.map(safe).to_csv(index=False).encode('utf-8')
