import os
import sys
import random
import unittest
from datetime import datetime, timedelta

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.models import FinancialProfile, FinancialEvent, Request, PaymentOption
from code.cashflow import CashFlowEngine, RecurringStream
from code.plans import PaymentPlanEngine
from code.optimizer import DecisionOptimizer
from code.resolver import UserMessageContext

class TestPropertiesAndFuzz(unittest.TestCase):
    def setUp(self):
        self.cf_engine = CashFlowEngine(horizon_days=90)
        self.plan_engine = PaymentPlanEngine()
        self.optimizer = DecisionOptimizer(self.cf_engine, self.plan_engine)
        self.empty_ctx = UserMessageContext()

    def _verify_invariants(self, req: Request, profile: FinancialProfile, plan, safe_amt: float):
        # Invariant 1: 0 <= safe_amt <= requested_amount
        self.assertGreaterEqual(safe_amt, 0.0, f"Safe amount {safe_amt} < 0")
        self.assertLessEqual(round(safe_amt, 2), round(req.requested_amount, 2), f"Safe amount {safe_amt} > requested {req.requested_amount}")

        # Invariant 2: If affordable_now, earliest_date == request_date
        if plan.affordability_status == "affordable_now":
            self.assertEqual(plan.earliest_date_for_full_payment, req.request_date)

        # Invariant 3: If partial_payment, 2 payments sum to requested_amount
        if plan.method == "partial_payment":
            self.assertEqual(len(plan.payment_schedule), 2)
            sum_sched = round(sum(a for _, a in plan.payment_schedule), 2)
            self.assertEqual(sum_sched, round(req.requested_amount, 2))
            self.assertEqual(round(plan.payment_schedule[0][1], 2), round(safe_amt, 2))
            self.assertLessEqual(plan.payment_schedule[1][0], req.desired_completion_date)

        # Invariant 4: If not_affordable, payment_plan is none
        if plan.affordability_status == "not_affordable":
            self.assertEqual(plan.payment_plan_str, "none")
            self.assertEqual(plan.method, "not_recommended")

        # Invariant 5: If plan recommended (not not_recommended), last payment date <= deadline
        if plan.method != "not_recommended":
            self.assertLessEqual(plan.last_payment_date, req.desired_completion_date)

    # PHASE 22: Invariants test across realistic parameter grid
    def test_22_systemic_invariants(self):
        currencies = ["USD", "EUR", "IDR", "INR"]
        methods_sets = [
            {"full_payment"},
            {"full_payment", "partial_payment"},
            {"full_payment", "partial_payment", "installments"},
            {"installments"}
        ]
        
        for curr in currencies:
            for methods in methods_sets:
                profile = FinancialProfile(
                    user_id="u_prop", home_currency=curr, current_available_balance=10000.0,
                    minimum_balance_to_keep=2000.0, payment_methods_user_will_consider=methods,
                    max_installment_months=6
                )
                req = Request(
                    request_id="r_prop", user_id="u_prop", request_date="2026-01-01",
                    request_type="discretionary", requested_amount=6000.0, desired_completion_date="2026-03-31",
                    allows_partial_payment=True, request_text="Item"
                )
                daily = self.cf_engine.simulate_daily_balances(profile, req.request_date, [], 0.0, [])
                safe = self.cf_engine.calculate_amount_safe_to_pay(daily, profile.minimum_balance_to_keep, req.requested_amount)
                plan = self.optimizer.evaluate_request(req, profile, [], [], self.empty_ctx)
                self._verify_invariants(req, profile, plan, safe)

    # PHASE 23: Fuzz Testing with 1,000 synthetic randomized scenarios
    def test_23_fuzz_1000_scenarios(self):
        random.seed(42)  # Deterministic seed for reproducible testing
        
        statuses = ["settled", "pending", "cancelled", "unrealized", "failed"]
        directions = ["debit", "credit"]
        categories = ["salary", "rent", "groceries", "transport", "shopping", "investment", "dining"]
        all_methods = ["full_payment", "partial_payment", "installments"]

        for i in range(1000):
            avail = random.uniform(0, 100000)
            min_bal = random.uniform(0, 50000)
            req_amt = random.uniform(10, 50000)
            
            num_methods = random.randint(1, 3)
            user_methods = set(random.sample(all_methods, num_methods))
            max_inst = random.choice([None, 3, 6, 12])

            profile = FinancialProfile(
                user_id=f"fuzz_u_{i}",
                home_currency="USD",
                current_available_balance=round(avail, 2),
                minimum_balance_to_keep=round(min_bal, 2),
                payment_methods_user_will_consider=user_methods,
                max_installment_months=max_inst
            )

            deadline_days = random.randint(1, 90)
            req_dt = "2026-01-01"
            deadline_dt = (datetime.strptime(req_dt, "%Y-%m-%d") + timedelta(days=deadline_days)).strftime("%Y-%m-%d")

            req = Request(
                request_id=f"fuzz_r_{i}",
                user_id=f"fuzz_u_{i}",
                request_date=req_dt,
                request_type="discretionary",
                requested_amount=round(req_amt, 2),
                desired_completion_date=deadline_dt,
                allows_partial_payment=random.choice([True, False]),
                request_text="Fuzz purchase"
            )

            # Generate random past/future events
            events = []
            num_events = random.randint(0, 8)
            for j in range(num_events):
                ev_days = random.randint(-60, 60)
                ev_date = (datetime.strptime(req_dt, "%Y-%m-%d") + timedelta(days=ev_days)).strftime("%Y-%m-%d")
                amt = random.uniform(10, 20000)
                events.append(FinancialEvent(
                    event_id=f"fuzz_e_{i}_{j}",
                    user_id=f"fuzz_u_{i}",
                    event_type="expense",
                    description="Fuzz event",
                    category=random.choice(categories),
                    direction=random.choice(directions),
                    amount=round(amt, 2),
                    currency="USD",
                    event_date=ev_date,
                    settlement_date=ev_date,
                    status=random.choice(statuses),
                    normalized_amount=round(amt, 2)
                ))

            # Generate random payment options
            opts = []
            if "installments" in user_methods:
                for k in range(random.randint(1, 3)):
                    num_p = random.choice([3, 6, 12])
                    p_amt = round(req_amt / num_p, 2)
                    opts.append(PaymentOption(
                        payment_option_id=f"opt_{i}_{k}",
                        request_id=req.request_id,
                        payment_method="installments",
                        number_of_payments=num_p,
                        payment_amount=p_amt,
                        payment_frequency_days=30,
                        first_payment_date=req_dt,
                        total_payable_amount=round(p_amt * num_p, 2),
                        financing_fee=0.0
                    ))

            # Execute simulation and optimization
            streams, var_rate = self.cf_engine.extract_recurring_streams(profile, events, self.empty_ctx, req_dt)
            fut_events = [e for e in events if e.settlement_date >= req_dt]
            daily = self.cf_engine.simulate_daily_balances(profile, req_dt, streams, var_rate, fut_events)
            safe = self.cf_engine.calculate_amount_safe_to_pay(daily, profile.minimum_balance_to_keep, req.requested_amount)
            plan = self.optimizer.evaluate_request(req, profile, events, opts, self.empty_ctx)

            self._verify_invariants(req, profile, plan, safe)

if __name__ == "__main__":
    unittest.main()
