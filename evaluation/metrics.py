"""Deterministic metrics. Undefined denominators are null, never invented scores."""


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def precision_recall(actual: set, expected: set):
    true_positive = len(actual & expected)
    return {'precision': ratio(true_positive, len(actual)), 'recall': ratio(true_positive, len(expected)),
            'true_positive': true_positive, 'false_positive': len(actual - expected),
            'false_negative': len(expected - actual)}


def aggregate_matches(results, name):
    values = [result[name] for result in results]
    tp = sum(value['true_positive'] for value in values)
    fp = sum(value['false_positive'] for value in values)
    fn = sum(value['false_negative'] for value in values)
    return {'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn),
            'true_positive': tp, 'false_positive': fp, 'false_negative': fn}
