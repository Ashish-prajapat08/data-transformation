"""CSV/Excel ingestion, preserving business identifiers as strings."""
from io import BytesIO, StringIO
import csv
from pathlib import Path
import os
import pandas as pd


def load_file(content: bytes, filename: str) -> pd.DataFrame:
    if not content or len(content) > int(os.getenv('MAX_UPLOAD_BYTES', '10485760')):
        raise ValueError('File is empty or exceeds upload limit')
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        header = next(csv.reader(StringIO(content.decode('utf-8-sig'))), [])
        if len(set(name.strip() for name in header)) != len(header) or any(not name.strip() for name in header):
            raise ValueError('Source columns must have distinct, nonempty names')
        df = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    elif suffix == '.xlsx':
        # Reject archive expansion bombs before passing the workbook to openpyxl.
        import zipfile
        with zipfile.ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError('Expanded workbook exceeds limit')
        raw = pd.read_excel(BytesIO(content), dtype=str, keep_default_na=False, header=None)
        if raw.empty:
            raise ValueError('Workbook is empty')
        df = raw.iloc[1:].copy()
        df.columns = list(raw.iloc[0])
    else:
        raise ValueError('Use a CSV or XLSX file')
    if len(df) > 100000 or len(df.columns) > 100:
        raise ValueError('V0 supports at most 100,000 rows and 100 columns')
    if df.empty:
        raise ValueError('Dataset must contain at least one row')
    df.columns = [str(column).strip() for column in df.columns]
    if len(set(df.columns)) != len(df.columns) or any(not col for col in df.columns):
        raise ValueError('Source columns must have distinct, nonempty names')
    return df.replace(r'^\s*$', None, regex=True).reset_index(drop=True)
