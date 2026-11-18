import re
import pandas as pd
from models.migration import Mapping, TargetSchema


def canonical(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def suggest_mappings(columns: list[str], target: TargetSchema) -> list[Mapping]:
    result = []
    for field in target.fields:
        matches = [col for col in columns if canonical(col) in
                   {canonical(field.name), *(canonical(alias) for alias in field.aliases)}]
        result.append(Mapping(source=matches[0] if len(matches) == 1 else None,
                              target=field.name, confidence=1 if len(matches) == 1 else 0,
                              reason='Unique field-name/alias match' if len(matches) == 1 else
                              'No unique safe mapping; human input required'))
    return result


def map_schema(df: pd.DataFrame, mappings: list[Mapping], target: TargetSchema) -> pd.DataFrame:
    return pd.DataFrame({mapping.target: df[mapping.source].copy() if mapping.source else
                         pd.Series(None, index=df.index, dtype=object) for mapping in mappings}, index=df.index)
