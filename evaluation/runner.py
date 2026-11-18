"""Run via python -m evaluation.runner. Every number comes from actual executions."""
import argparse
import json
from io import BytesIO
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
import pandas as pd
from agent.graph import MigrationAgent
from agent.planning import RulesPlanner, configured_planner
from backend.persistence import Store
from backend.service import MigrationService
from models.migration import ReviewDecision
from evaluation.generators.problems import scenarios
from evaluation.evaluators.quality import evaluate_scenario
from evaluation.metrics import aggregate_matches, ratio


def run_evaluation(planner=None):
    start = perf_counter()
    planner = planner or RulesPlanner()
    store = Store('sqlite:///:memory:')
    service = MigrationService(store=store, agent=MigrationAgent(planner))
    results = []
    try:
        for scenario in scenarios():
            state = service.create(scenario.source.to_csv(index=False).encode(), scenario.name + '.csv', scenario.target)
            initial = state.migration_plan
            if initial is None:
                raise ValueError('Evaluation planning failed; no quality scores can be computed')
            # No oracle corrections. Policy approves only plans with no uncertain mappings.
            if state.status == 'awaiting_plan' and not state.review_items:
                state = service.approve(state.run_id, True)
            # Simulated human policy explicitly keeps all entity candidates separate.
            decisions = [ReviewDecision(item_id=item.id, action='keep') for item in state.review_items
                         if item.kind == 'entity' and item.decision is None]
            if decisions and state.status == 'awaiting_review':
                state = service.review(state.run_id, decisions)
            exported = None
            if state.status == 'ready':
                exported = pd.read_csv(BytesIO(service.export(state.run_id)), dtype=str, keep_default_na=False)
                state, _ = store.load(state.run_id)
            result = evaluate_scenario(scenario, state, initial, exported)
            state.evaluation_results = result
            _, version = store.load(state.run_id)
            store.save(state, version)
            results.append(result)
    finally:
        store.engine.dispose()
    count = len(results)
    return {'created_at': datetime.now(timezone.utc).isoformat(), 'planner': type(planner).__name__,
            'fixture_count': count, 'elapsed_seconds': round(perf_counter() - start, 4),
            'review_policy': 'Approve unambiguous plans; keep entity candidates separate; never repair invalid facts from ground truth',
            'metrics': {'task_success_rate': ratio(sum(result['task_success'] for result in results), count),
                'schema_mapping_accuracy': ratio(sum(result['schema_mapping_accuracy'] for result in results), count),
                'transformation_accuracy': ratio(sum(result['correct_cells'] for result in results),
                                                 sum(result['evaluated_cells'] for result in results)),
                'duplicate_detection': aggregate_matches(results, 'duplicate_detection'),
                'entity_matching': aggregate_matches(results, 'entity_matching'),
                'validation_accuracy': ratio(sum(result['validation_accuracy'] for result in results), count),
                'safety_outcome_accuracy': ratio(sum(result['safety_outcome_correct'] for result in results), count),
                'retry_rate': ratio(sum(result['retry_count'] > 0 for result in results), count),
                'human_review_rate': ratio(sum(result['human_review_required'] for result in results), count)},
            'scenarios': results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--planner', choices=['rules', 'configured'], default='rules')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.planner == 'configured':
        from dotenv import load_dotenv
        load_dotenv()
    result = run_evaluation(configured_planner() if args.planner == 'configured' else RulesPlanner())
    output = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + '\n')
    print(output)


if __name__ == '__main__':
    main()
