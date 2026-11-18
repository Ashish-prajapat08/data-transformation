"""Blocked candidate generation. Every entity merge needs a human decision."""
import re
from collections import defaultdict
from difflib import SequenceMatcher
import pandas as pd
from models.migration import ReviewItem
from tools.profiling import missing


def entity_key(value: str) -> str:
    value = value.casefold()
    value = re.sub(r'\b(pvt|private|ltd|limited|inc|incorporated)\b\.?', '', value)
    return re.sub(r'[^a-z0-9]', '', value)


def resolve_entities(df: pd.DataFrame, column: str | None) -> list[ReviewItem]:
    if column is None:
        return []
    blocks = defaultdict(list)
    matches = []
    comparisons = 0
    for row, value in df[column].items():
        if missing(value):
            continue
        key = entity_key(str(value))
        if not key:
            continue
        block = key[:3]
        for other_row, other_key in blocks[block][-100:]:
            comparisons += 1
            if comparisons > 100000 or len(matches) >= 500:
                raise ValueError('Entity candidate limit exceeded; split the dataset for V0 review')
            confidence = SequenceMatcher(None, key, other_key).ratio()
            if confidence >= .86:
                matches.append(ReviewItem(id=f'entity:{other_row}:{row}', kind='entity', column=column,
                    rows=[int(other_row), int(row)], confidence=round(confidence, 3),
                    reason='Similar normalized organization names; name similarity alone does not establish identity',
                    recommendation='Inspect both records; keep separate unless they are the same record',
                    actions=['keep', 'merge']))
        blocks[block].append((row, key))
    return matches
