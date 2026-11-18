from datetime import date
from decimal import Decimal, InvalidOperation
import re
import pandas as pd
from models.migration import TargetSchema, ValidationIssue, ValidationResult
from tools.profiling import EMAIL, PHONE, missing


def valid_kind(value, field) -> bool:
    if missing(value):
        return True
    text = str(value)
    if field.kind == 'email':
        return bool(EMAIL.fullmatch(text))
    if field.kind == 'phone':
        return bool(PHONE.fullmatch(text))
    if field.kind == 'date':
        try:
            return date.fromisoformat(text).isoformat() == text
        except ValueError:
            return False
    if field.kind == 'integer':
        return bool(re.fullmatch(r'[+-]?\d+', text))
    if field.kind == 'number':
        try:
            return Decimal(text).is_finite()
        except InvalidOperation:
            return False
    if field.kind == 'boolean':
        return text in ('true', 'false')
    if field.kind == 'category':
        return text in field.allowed
    return True


def validate_data(df: pd.DataFrame, target: TargetSchema) -> ValidationResult:
    issues = []
    expected = {field.name for field in target.fields}
    for col in set(df.columns) - expected:
        issues.append(ValidationIssue(code='unexpected_column', column=col, message='Unexpected target column'))
    for field in target.fields:
        if field.name not in df:
            issues.append(ValidationIssue(code='missing_column', column=field.name, message='Target column absent'))
            continue
        series = df[field.name]
        checks = {'invalid_' + field.kind: ~series.map(lambda value: valid_kind(value, field))}
        if field.required:
            checks['required'] = series.map(missing)
        if field.unique:
            checks['unique'] = series.duplicated(keep=False) & ~series.map(missing)
        for code, mask in checks.items():
            rows = [int(index) for index in series.index[mask]]
            if rows:
                issues.append(ValidationIssue(code=code, column=field.name, rows=rows,
                                              message=f'{len(rows)} records fail {code}'))
    bad_cells = {(issue.column, row) for issue in issues for row in issue.rows}
    structural = any(not issue.rows for issue in issues)
    readiness = 0 if structural or df.empty else round(100 * (1 - len(bad_cells) / max(1, df.size)), 2)
    return ValidationResult(passed=not issues and not df.empty, issues=issues, readiness=readiness)
