import pandas as pd
from evaluation.metrics import precision_recall, ratio


def evaluate_scenario(scenario, state, initial_plan, exported):
    mapping_correct = sum(scenario.expected_mapping.get(item.target) == item.source for item in initial_plan.mappings)
    duplicate_rows = {row for event in state.trace if event.action == 'detect_duplicates'
                      for row in event.metadata.get('removed_rows', [])}
    entity_pairs = {tuple(item.rows) for item in state.review_items if item.kind == 'entity'}
    correct_cells = total_cells = 0
    if scenario.expected is not None:
        # Compare exported content independently against declared clean ground truth.
        actual = exported.reset_index(drop=True) if exported is not None else state.frame.reset_index(drop=True)
        expected = scenario.expected.reset_index(drop=True)
        total_cells = expected.size
        if list(actual.columns) == list(expected.columns) and actual.shape == expected.shape:
            correct_cells = int((actual.fillna('').astype(str) == expected.fillna('').astype(str)).sum().sum())
    valid = bool(state.validation_results and state.validation_results.passed)
    return {'name': scenario.name, 'status': state.status, 'task_success': state.status == 'ready' and exported is not None,
            'schema_mapping_accuracy': ratio(mapping_correct, len(scenario.expected_mapping)),
            'transformation_accuracy': ratio(correct_cells, total_cells),
            'correct_cells': correct_cells, 'evaluated_cells': total_cells,
            'duplicate_detection': precision_recall(duplicate_rows, scenario.duplicate_rows),
            'entity_matching': precision_recall(entity_pairs, scenario.entity_pairs),
            'validation_accuracy': int(valid == scenario.expected_valid),
            'safety_outcome_correct': (state.status == 'ready') == scenario.expected_valid,
            'retry_count': state.retry_count,
            'human_review_required': bool(state.review_items),
            'tool_call_count': sum(event.node == 'execute' for event in state.trace),
            'issues': [issue.model_dump() for issue in state.validation_results.issues] if state.validation_results else [],
            'errors': state.errors}
