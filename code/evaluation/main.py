import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import csv
from typing import Dict, List, Tuple
from code.ingestion import DatasetLoader
from code.resolver import InformationResolver
from code.cashflow import CashFlowEngine
from code.plans import PaymentPlanEngine
from code.optimizer import DecisionOptimizer
from code.explanation import ExplanationGenerator

def evaluate_samples(data_dir: str = 'dataset') -> Dict[str, float]:
    loader = DatasetLoader(data_dir=data_dir)
    loader.load_all()
    
    resolver = InformationResolver()
    resolver.resolve_image_events(loader)
    
    cf_engine = CashFlowEngine()
    plan_engine = PaymentPlanEngine()
    optimizer = DecisionOptimizer(cf_engine, plan_engine)
    exp_gen = ExplanationGenerator()

    sample_path = os.path.join(data_dir, 'sample_requests.csv')
    with open(sample_path, encoding='utf-8') as f:
        ground_truth = list(csv.DictReader(f))

    total = len(ground_truth)
    metrics = {
        'status_matches': 0,
        'method_matches': 0,
        'plan_matches': 0,
        'changes_matches': 0,
        'earliest_matches': 0
    }

    print('Evaluating', total, 'public sample requests...')
    print('=' * 70)

    for row in ground_truth:
        req_id = row['request_id']
        uid = row['user_id']
        
        req = loader.load_requests('sample_requests.csv')
        r_obj = next(r for r in req if r.request_id == req_id)
        profile = loader.profiles[uid]
        events = loader.events_by_user[uid]
        opts = loader.payment_options.get(req_id, [])
        msg_ctx = resolver.parse_user_messages(loader.messages_by_user.get(uid, []))

        plan = optimizer.evaluate_request(r_obj, profile, events, opts, msg_ctx)

        exp_status = row['affordability_status']
        exp_method = row['recommended_payment_method']
        exp_plan = row['payment_plan']
        exp_changes = row['spending_changes_needed']
        exp_earliest = row['earliest_date_for_full_payment'].strip() or None
        exp_safe = float(row['amount_safe_to_pay'])

        status_ok = (plan.affordability_status == exp_status)
        method_ok = (plan.method == exp_method)
        plan_ok = (plan.payment_plan_str == exp_plan)
        changes_ok = (plan.spending_changes_str == exp_changes)
        earliest_ok = (plan.earliest_date_for_full_payment == exp_earliest)

        if status_ok: metrics['status_matches'] += 1
        if method_ok: metrics['method_matches'] += 1
        if plan_ok: metrics['plan_matches'] += 1
        if changes_ok: metrics['changes_matches'] += 1
        if earliest_ok: metrics['earliest_matches'] += 1

        status_symbol = 'MATCH' if (status_ok and method_ok and plan_ok and changes_ok) else 'DIFF'
        print(status_symbol, req_id, 'status:', plan.affordability_status, 'exp:', exp_status, 'method:', plan.method, 'exp:', exp_method)

    print('=' * 70)
    print('Affordability Status Accuracy:', metrics['status_matches'], '/', total)
    print('Payment Method Accuracy:      ', metrics['method_matches'], '/', total)
    print('Payment Plan Accuracy:        ', metrics['plan_matches'], '/', total)
    print('Spending Changes Accuracy:    ', metrics['changes_matches'], '/', total)
    print('Earliest Date Accuracy:       ', metrics['earliest_matches'], '/', total)

    return metrics

if __name__ == '__main__':
    evaluate_samples()
