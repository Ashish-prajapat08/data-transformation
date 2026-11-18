import pandas as pd


def detect_duplicates(df: pd.DataFrame) -> list[int]:
    return [int(index) for index in df.index[df.duplicated(keep='first')]]


def remove_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop_duplicates(keep='first').copy()
