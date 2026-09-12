import os
import sys
import csv
from datetime import datetime

# Ensure repository root is on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.models import FinancialProfile, FinancialEvent, Request, PaymentOption
from code.ingestion import DatasetLoader
from code.resolver import InformationResolver
from code.cashflow import CashFlowEngine
from code.plans import PaymentPlanEngine
from code.optimizer import DecisionOptimizer
from code.explanation import ExplanationGenerator

def format_amount(amt: float) -> str:
    amt_r = round(amt, 2)
    if amt_r == int(amt_r):
        return str(int(amt_r))
    return f"{amt_r:.2f}".rstrip("0").rstrip(".")

def run_pipeline(data_dir: str = "dataset", output_paths=None):
    if output_paths is None:
        output_paths = ["output.csv", os.path.join(data_dir, "output.csv")]
        
    print("=" * 70)
    print("Running Buy or Wait? Financial Decision Agent Pipeline")
    print("=" * 70)

    loader = DatasetLoader(data_dir=data_dir)
    loader.load_all()

    resolver = InformationResolver()
    resolver.resolve_image_events(loader)

    cf_engine = CashFlowEngine()
    plan_engine = PaymentPlanEngine()
    optimizer = DecisionOptimizer(cf_engine, plan_engine)
    exp_gen = ExplanationGenerator()

    eval_requests = loader.load_requests("requests.csv")
    print(f"Loaded {len(eval_requests)} evaluation requests.")

    fieldnames = [
        "request_id",
        "amount_safe_to_pay",
        "affordability_status",
        "recommended_payment_method",
        "payment_plan",
        "earliest_date_for_full_payment",
        "spending_changes_needed",
        "decision_explanation"
    ]

    output_rows = []

    for req in eval_requests:
        uid = req.user_id
        profile = loader.profiles[uid]
        events = loader.events_by_user.get(uid, [])
        options = loader.payment_options.get(req.request_id, [])
        user_msgs = loader.messages_by_user.get(uid, [])
        msg_ctx = resolver.parse_user_messages(user_msgs)

        # 1. Base safety calculation
        streams, var_rate = cf_engine.extract_recurring_streams(
            profile, events, msg_ctx, req.request_date
        )
        future_events = [e for e in events if e.settlement_date >= req.request_date]
        base_daily = cf_engine.simulate_daily_balances(
            profile, req.request_date, streams, var_rate, future_events
        )
        base_safe = cf_engine.calculate_amount_safe_to_pay(
            base_daily, profile.minimum_balance_to_keep, req.requested_amount
        )

        # 2. Evaluate optimal recommendation
        best_plan = optimizer.evaluate_request(
            req, profile, events, options, msg_ctx
        )

        # 3. Generate natural, fact-grounded explanation
        events_by_id = {e.event_id: e for e in events}
        explanation = exp_gen.generate_explanation(
            best_plan, req, profile, events_by_id
        )

        # 4. Earliest date string
        earliest_str = best_plan.earliest_date_for_full_payment if best_plan.earliest_date_for_full_payment else ""

        output_rows.append({
            "request_id": req.request_id,
            "amount_safe_to_pay": format_amount(base_safe),
            "affordability_status": best_plan.affordability_status,
            "recommended_payment_method": best_plan.method,
            "payment_plan": best_plan.payment_plan_str,
            "earliest_date_for_full_payment": earliest_str,
            "spending_changes_needed": best_plan.spending_changes_str,
            "decision_explanation": explanation
        })

    for out_path in output_paths:
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
        print(f"Successfully generated {out_path} ({len(output_rows)} rows).")

    print("Pipeline run complete!")

if __name__ == "__main__":
    run_pipeline()
