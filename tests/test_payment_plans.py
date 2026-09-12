import os
import sys
import unittest
from datetime import datetime, timedelta

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.models import FinancialProfile, FinancialEvent, Request, PaymentOption
from code.cashflow import CashFlowEngine, RecurringStream
from code.plans import PaymentPlanEngine, CandidatePlan
from code.optimizer import DecisionOptimizer
from code.resolver import UserMessageContext

def make_profile(
    avail: float = 10000.0,
    min_b: float = 2000.0,
    methods: set = None,
    max_inst: int = None,
    curr: str = "USD"
) -> FinancialProfile:
    if methods is None:
        methods = {"full_payment", "partial_payment", "installments"}
    return FinancialProfile(
        user_id="synth_user",
        home_currency=curr,
        current_available_balance=avail,
        minimum_balance_to_keep=min_b,
        financial_priorities=["emergency_savings"],
        expense_categories_to_protect={"rent", "groceries"},
        expense_categories_user_is_willing_to_reduce=set(),
        expense_categories_user_is_willing_to_stop=set(),
        payment_methods_user_will_consider=methods,
        max_installment_months=max_inst
    )

def make_request(
    amount: float = 5000.0,
    req_date: str = "2026-01-01",
    deadline: str = "2026-03-31",
    partial_ok: bool = True
) -> Request:
    return Request(
        request_id="req_test_01",
        user_id="synth_user",
        request_date=req_date,
        request_type="discretionary",
        requested_amount=amount,
        desired_completion_date=deadline,
        allows_partial_payment=partial_ok,
        request_text="Laptop purchase"
    )

class TestPaymentPlans(unittest.TestCase):
    def setUp(self):
        self.cf_engine = CashFlowEngine(horizon_days=90)
        self.plan_engine = PaymentPlanEngine()
        self.optimizer = DecisionOptimizer(self.cf_engine, self.plan_engine)
        self.empty_ctx = UserMessageContext()

    # PHASE 9: Full payment strategy tests
    def test_9_full_payment_immediate_affordability(self):
        p = make_profile(avail=10000.0, min_b=2000.0)
        r = make_request(amount=5000.0)
        plan = self.optimizer.evaluate_request(r, p, [], [], self.empty_ctx)
        
        self.assertEqual(plan.method, "full_payment")
        self.assertEqual(plan.affordability_status, "affordable_now")
        self.assertEqual(plan.payment_plan_str, "2026-01-01:5000")
        self.assertEqual(plan.earliest_date_for_full_payment, "2026-01-01")
        self.assertEqual(plan.spending_changes_str, "none")
        self.assertEqual(plan.number_of_payments, 1)

    # PHASE 10: Partial payment strategy tests
    def test_10_partial_payment_two_payment_rule(self):
        # Balance = 5000, Min = 2000 -> Safe amount = 3000
        # Request = 5000
        # Salary on Jan 15 of 10000 -> earliest date for full payment is 2026-01-15
        p = make_profile(avail=5000.0, min_b=2000.0, methods={"full_payment", "partial_payment"})
        r = make_request(amount=5000.0, req_date="2026-01-01", deadline="2026-01-31", partial_ok=True)
        
        sal_event = FinancialEvent(
            event_id="sal_1", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2026-01-15", settlement_date="2026-01-15", status="settled", normalized_amount=10000.0
        )
        prev_sal = FinancialEvent(
            event_id="sal_0", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2025-12-15", settlement_date="2025-12-15", status="settled", normalized_amount=10000.0
        )
        
        plan = self.optimizer.evaluate_request(r, p, [prev_sal, sal_event], [], self.empty_ctx)
        
        self.assertEqual(plan.method, "partial_payment")
        self.assertEqual(plan.affordability_status, "affordable_with_plan")
        self.assertEqual(plan.payment_plan_str, "2026-01-01:3000|2026-01-15:2000")
        self.assertEqual(plan.number_of_payments, 2)
        # Sum must equal requested amount exactly
        sum_payments = sum(amt for _, amt in plan.payment_schedule)
        self.assertEqual(sum_payments, r.requested_amount)

    def test_10_partial_payment_disallowed_when_request_forbids(self):
        # Same scenario as above, but allows_partial_payment is False
        p = make_profile(avail=5000.0, min_b=2000.0, methods={"full_payment", "partial_payment"})
        r = make_request(amount=5000.0, req_date="2026-01-01", deadline="2026-01-31", partial_ok=False)
        
        sal_event = FinancialEvent(
            event_id="sal_1", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2026-01-15", settlement_date="2026-01-15", status="settled", normalized_amount=10000.0
        )
        prev_sal = FinancialEvent(
            event_id="sal_0", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2025-12-15", settlement_date="2025-12-15", status="settled", normalized_amount=10000.0
        )
        
        plan = self.optimizer.evaluate_request(r, p, [prev_sal, sal_event], [], self.empty_ctx)
        # Must wait until salary on Jan 15 since partial payment is forbidden by request
        self.assertEqual(plan.method, "wait")
        self.assertEqual(plan.affordability_status, "affordable_later")
        self.assertEqual(plan.payment_plan_str, "2026-01-15:5000")

    def test_10_partial_payment_disallowed_when_user_rejects_method(self):
        # User only considers full_payment
        p = make_profile(avail=5000.0, min_b=2000.0, methods={"full_payment"})
        r = make_request(amount=5000.0, req_date="2026-01-01", deadline="2026-01-31", partial_ok=True)
        
        sal_event = FinancialEvent(
            event_id="sal_1", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2026-01-15", settlement_date="2026-01-15", status="settled", normalized_amount=10000.0
        )
        prev_sal = FinancialEvent(
            event_id="sal_0", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2025-12-15", settlement_date="2025-12-15", status="settled", normalized_amount=10000.0
        )
        
        plan = self.optimizer.evaluate_request(r, p, [prev_sal, sal_event], [], self.empty_ctx)
        self.assertEqual(plan.method, "wait")
        self.assertEqual(plan.affordability_status, "affordable_later")

    # PHASE 11: Installment strategy & provider option tests
    def test_11_installments_selected_when_affordable(self):
        p = make_profile(avail=3000.0, min_b=2000.0, methods={"installments"}, max_inst=3)
        r = make_request(amount=3000.0, req_date="2026-01-01", deadline="2026-04-01")
        opts = [
            PaymentOption(
                payment_option_id="opt_inst_3", request_id=r.request_id, payment_method="installments",
                number_of_payments=3, payment_amount=1000.0, payment_frequency_days=30,
                first_payment_date="2026-01-01", total_payable_amount=3000.0, financing_fee=0.0
            )
        ]
        # User has 3000 avail, 2000 min balance. Paying 1000 on Jan 1 leaves 2000, safe!
        # Plus salary on Jan 20 provides replenishing funds
        sal_event = FinancialEvent(
            event_id="sal_1", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=5000.0, currency="USD",
            event_date="2026-01-20", settlement_date="2026-01-20", status="settled", normalized_amount=5000.0
        )
        prev_sal = FinancialEvent(
            event_id="sal_0", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=5000.0, currency="USD",
            event_date="2025-12-20", settlement_date="2025-12-20", status="settled", normalized_amount=5000.0
        )
        
        plan = self.optimizer.evaluate_request(r, p, [prev_sal, sal_event], opts, self.empty_ctx)
        self.assertEqual(plan.method, "installments")
        self.assertEqual(plan.affordability_status, "affordable_with_plan")
        self.assertEqual(plan.number_of_payments, 3)
        self.assertEqual(plan.payment_option_id, "opt_inst_3")

    def test_11_installments_rejected_if_exceeding_max_installment_months(self):
        # User max_installment_months is 2, option requires 6
        p = make_profile(avail=3000.0, min_b=2000.0, methods={"installments"}, max_inst=2)
        r = make_request(amount=6000.0, req_date="2026-01-01", deadline="2026-07-01")
        opts = [
            PaymentOption(
                payment_option_id="opt_inst_6", request_id=r.request_id, payment_method="installments",
                number_of_payments=6, payment_amount=1000.0, payment_frequency_days=30,
                first_payment_date="2026-01-01", total_payable_amount=6000.0, financing_fee=0.0
            )
        ]
        plan = self.optimizer.evaluate_request(r, p, [], opts, self.empty_ctx)
        self.assertEqual(plan.method, "not_recommended")
        self.assertEqual(plan.affordability_status, "not_affordable")

    # PHASE 12: Desired completion date & deadline tests
    def test_12_plan_rejected_if_past_desired_completion_date(self):
        # Salary arrives on Jan 25, but user deadline is Jan 10
        p = make_profile(avail=3000.0, min_b=2000.0, methods={"full_payment", "partial_payment"})
        r = make_request(amount=5000.0, req_date="2026-01-01", deadline="2026-01-10", partial_ok=True)
        
        sal_event = FinancialEvent(
            event_id="sal_1", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2026-01-25", settlement_date="2026-01-25", status="settled", normalized_amount=10000.0
        )
        prev_sal = FinancialEvent(
            event_id="sal_0", user_id=p.user_id, event_type="income", description="Monthly Salary",
            category="salary", direction="credit", amount=10000.0, currency="USD",
            event_date="2025-12-25", settlement_date="2025-12-25", status="settled", normalized_amount=10000.0
        )
        
        plan = self.optimizer.evaluate_request(r, p, [prev_sal, sal_event], [], self.empty_ctx)
        # Cannot finish by Jan 10!
        self.assertEqual(plan.method, "not_recommended")
        self.assertEqual(plan.affordability_status, "not_affordable")
        self.assertEqual(plan.payment_plan_str, "none")

if __name__ == "__main__":
    unittest.main()
