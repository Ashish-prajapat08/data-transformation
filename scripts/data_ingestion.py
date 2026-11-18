"""Existing file-ingestion interface retained. Public arbitrary SQL/API input is retired."""
from pathlib import Path
from tools.ingestion import load_file

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'


class DataIngestion:
    def __init__(self, db_url=None):
        if db_url:
            raise ValueError('Use DATABASE_URL for application persistence; V0 intake supports CSV/Excel')

    def load_csv(self, file_name):
        path = DATA_DIR / file_name
        return load_file(path.read_bytes(), path.name)

    def load_excel(self, file_name, sheet_name=0):
        if sheet_name != 0:
            raise ValueError('V0 imports the first workbook sheet')
        path = DATA_DIR / file_name
        return load_file(path.read_bytes(), path.name)
