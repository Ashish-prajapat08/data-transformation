"""Compatibility facade over deterministic tools; no implicit business-data imputation."""
from tools.duplicates import remove_exact_duplicates
from tools.transformations import handle_missing_values, convert_data_type


class DataCleaning:
    def handle_missing_values(self, df, rule):
        result = df.copy()
        result[rule.name] = handle_missing_values(result[rule.name], rule)
        return result

    def remove_duplicates(self, df):
        return remove_exact_duplicates(df)

    def fix_data_types(self, df, rules):
        result = df.copy()
        for rule in rules:
            if rule.kind in ('integer', 'number', 'boolean'):
                result[rule.name] = result[rule.name].map(lambda value: convert_data_type(value, rule.kind))
        return result

    def clean_data(self, df):
        return self.remove_duplicates(df)
