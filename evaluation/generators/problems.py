"""Repeatable injected scenarios with independently declared ground truth."""
from dataclasses import dataclass, field
import pandas as pd
from models.migration import FieldRule, TargetSchema


@dataclass
class Scenario:
    name: str
    source: pd.DataFrame
    target: TargetSchema
    expected: pd.DataFrame | None
    expected_valid: bool
    expected_mapping: dict[str, str | None]
    duplicate_rows: set[int] = field(default_factory=set)
    entity_pairs: set[tuple[int, int]] = field(default_factory=set)


def scenarios() -> list[Scenario]:
    target = TargetSchema(name='Evaluation contacts', fields=[
        FieldRule(name='id', kind='integer', required=True, unique=True, aliases=['customer_id']),
        FieldRule(name='name', required=True, aliases=['customer_name']),
        FieldRule(name='email', kind='email', required=True, aliases=['email_address']),
        FieldRule(name='phone', kind='phone', aliases=['mobile']),
        FieldRule(name='date', kind='date', date_order='dayfirst', aliases=['joined']),
        FieldRule(name='status', kind='category', allowed=['active', 'inactive'], category_map={'enabled': 'active'}),
        FieldRule(name='company'),
    ], entity_field='company')
    clean = pd.DataFrame([
        ['1', 'Ada', 'ada@example.com', '+14155550101', '2024-03-02', 'active', 'ABC Private Limited'],
        ['2', 'Ben', 'ben@example.com', '+14155550102', '2024-05-21', 'inactive', 'Orbit'],
        ['3', 'Cara', 'cara@example.com', '+14155550103', '2024-07-11', 'active', 'Delta'],
    ], columns=[f.name for f in target.fields])
    mapping = {f.name: f.name for f in target.fields}
    messy = clean.copy()
    messy.loc[0, 'name'] = ' Ada  '
    messy.loc[0, 'email'] = ' ADA@EXAMPLE.COM '
    messy.loc[0, 'phone'] = '+1 (415) 555-0101'
    messy.loc[0, 'date'] = '02/03/2024'
    messy.loc[0, 'status'] = 'enabled'
    messy.loc[0, 'id'] = '1.0'
    renamed = {'id': 'customer_id', 'name': 'customer_name', 'email': 'email_address', 'phone': 'mobile', 'date': 'joined'}
    messy = pd.concat([messy, messy.iloc[[1]]], ignore_index=True).rename(columns=renamed)
    expected_mapping = {name: renamed.get(name, name) for name in mapping}
    invalid = clean.copy()
    invalid.loc[0, 'email'] = 'ada.example.com'
    invalid.loc[1, 'name'] = None
    invalid.loc[2, 'status'] = 'not-a-valid-category'
    invalid.loc[2, 'id'] = 'three'
    invalid.loc[2, 'date'] = '31/02/2024'
    entities = pd.concat([clean, clean.iloc[[0]]], ignore_index=True)
    entities.loc[3, ['id', 'email', 'company']] = ['4', 'other@example.com', 'ABC PVT. LTD.']
    return [Scenario('clean', clean, target, clean, True, mapping),
            Scenario('repairable_injection', messy, target, clean, True, expected_mapping, {3}),
            Scenario('unsafe_injection', invalid, target, None, False, mapping),
            Scenario('entity_variation', entities, target, entities, True, mapping, entity_pairs={(0, 3)})]
