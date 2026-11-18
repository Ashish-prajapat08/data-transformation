import pandas as pd
import pytest
from models.migration import FieldRule, TargetSchema
from tools.ingestion import load_file
from tools.transformations import normalize_email, normalize_phone, normalize_date
from tools.validation import validate_data
from tools.entity_resolution import resolve_entities
from tools.export import export_data


def test_normalization_preserves_uncertainty():
    assert normalize_email(' A@EXAMPLE.COM ') == 'a@example.com'
    assert normalize_phone('+1 (415) 555-0100') == '+14155550100'
    assert normalize_phone('555-1234 ext 9') == '555-1234 ext 9'
    assert normalize_date('02/03/2024') == '02/03/2024'
    assert normalize_date('02/03/2024', 'dayfirst') == '2024-03-02'
    assert normalize_date('31/02/2024') == '31/02/2024'


def test_ingestion_identifiers_and_nulls():
    df = load_file(b'id,email\n001,\n002,NA\n', 'test.csv')
    assert df.iloc[0]['id'] == '001'
    assert df.iloc[0]['email'] is None
    assert df.iloc[1]['email'] == 'NA'


def test_validation_and_export_gate():
    target = TargetSchema(fields=[FieldRule(name='email', kind='email', required=True, unique=True)])
    bad = pd.DataFrame({'email': ['x', None, 'a@b.com', 'a@b.com']})
    result = validate_data(bad, target)
    assert {issue.code for issue in result.issues} == {'invalid_email', 'required', 'unique'}
    with pytest.raises(ValueError):
        export_data(bad, target)
    with pytest.raises(ValueError):
        export_data(pd.DataFrame({'email': ['a@b.com']}), target, True)


def test_entity_candidates_require_review():
    reviews = resolve_entities(pd.DataFrame({'company': ['ABC Pvt Ltd', 'ABC Private Limited', 'Other']}), 'company')
    assert len(reviews) == 1
    assert reviews[0].rows == [0, 1]
    assert reviews[0].decision is None


def test_duplicate_headers_are_not_silently_renamed():
    with pytest.raises(ValueError, match='distinct'):
        load_file(b'email,email\na@b.com,c@d.com\n', 'source.csv')


def test_explicit_date_locale_is_respected():
    assert normalize_date('13/02/2024', 'monthfirst') == '13/02/2024'
    assert normalize_date('02/13/2024', 'dayfirst') == '02/13/2024'


def test_formula_export_protection():
    target = TargetSchema(fields=[FieldRule(name='name')])
    exported = export_data(pd.DataFrame({'name': ['=HYPERLINK("evil")', '+14155550101']}), target).decode()
    assert "'=HYPERLINK" in exported
    assert '+14155550101' in exported
