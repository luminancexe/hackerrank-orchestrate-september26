import os
import sys
import unittest
from datetime import datetime, timedelta

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.models import FinancialProfile, FinancialEvent, Request
from code.cashflow import CashFlowEngine, RecurringStream
from code.resolver import UserMessageContext

def make_profile(avail: float = 10000.0, min_b: float = 2000.0, curr: str = "USD") -> FinancialProfile:
    return FinancialProfile(
        user_id="synth_user",
        home_currency=curr,
        current_available_balance=avail,
        minimum_balance_to_keep=min_b,
        financial_priorities=["emergency_savings"],
        expense_categories_to_protect={"rent", "groceries"},
        expense_categories_user_is_willing_to_reduce=set(),
        expense_categories_user_is_willing_to_stop=set(),
        payment_methods_user_will_consider={"full_payment"},
        max_installment_months=None
    )

class TestCashFlow(unittest.TestCase):
    def setUp(self):
        self.engine = CashFlowEngine(horizon_days=90)

    # PHASE 3: TEST A - Simple affordable purchase
    def test_3A_simple_affordable_purchase(self):
        p = make_profile(avail=10000.0, min_b=2000.0)
        daily = self.engine.simulate_daily_balances(p, "2026-01-01", [], 0.0, [])
        safe = self.engine.calculate_amount_safe_to_pay(daily, p.minimum_balance_to_keep, 5000.0)
        self.assertEqual(safe, 5000.0)
        earliest = self.engine.find_earliest_date_for_full_payment(daily, p.minimum_balance_to_keep, 5000.0, "2026-01-01")
        self.assertEqual(earliest, "2026-01-01")

    # PHASE 3: TEST B - Minimum balance violation
    def test_3B_minimum_balance_violation(self):
        p = make_profile(avail=10000.0, min_b=2000.0)
        daily = self.engine.simulate_daily_balances(p, "2026-01-01", [], 0.0, [])
        safe = self.engine.calculate_amount_safe_to_pay(daily, p.minimum_balance_to_keep, 9000.0)
        self.assertEqual(safe, 8000.0)  # 10000 - 2000 = 8000
        earliest = self.engine.find_earliest_date_for_full_payment(daily, p.minimum_balance_to_keep, 9000.0, "2026-01-01")
        self.assertIsNone(earliest)

    # PHASE 3: TEST C - Future expense collision
    def test_3C_future_expense_collision(self):
        p = make_profile(avail=10000.0, min_b=2000.0)
        future_ev = [
            FinancialEvent(
                event_id="fe_1", user_id=p.user_id, event_type="expense", description="Mandatory Tax",
                category="taxes", direction="debit", amount=4000.0, currency="USD",
                event_date="2026-01-10", settlement_date="2026-01-10", status="scheduled", normalized_amount=4000.0
            )
        ]
        daily = self.engine.simulate_daily_balances(p, "2026-01-01", [], 0.0, future_ev)
        safe = self.engine.calculate_amount_safe_to_pay(daily, p.minimum_balance_to_keep, 7000.0)
        self.assertEqual(safe, 4000.0)  # Min balance in horizon is 6000, 6000 - 2000 = 4000
        earliest = self.engine.find_earliest_date_for_full_payment(daily, p.minimum_balance_to_keep, 7000.0, "2026-01-01")
        self.assertIsNone(earliest)

    # PHASE 3: TEST D - Future salary makes purchase affordable
    def test_3D_future_salary_makes_purchase_affordable(self):
        p = make_profile(avail=5000.0, min_b=2000.0)
        sal_stream = RecurringStream(
            category="salary", description="Confirmed Salary", day_of_month=11, amount=10000.0, is_income=True
        )
        daily = self.engine.simulate_daily_balances(p, "2026-01-01", [sal_stream], 0.0, [])
        safe = self.engine.calculate_amount_safe_to_pay(daily, p.minimum_balance_to_keep, 8000.0)
        self.assertEqual(safe, 3000.0)  # Safe today before salary is 5000 - 2000 = 3000
        earliest = self.engine.find_earliest_date_for_full_payment(daily, p.minimum_balance_to_keep, 8000.0, "2026-01-01", salary_day=11)
        self.assertEqual(earliest, "2026-01-11")

    # PHASE 3: TEST E - Salary arrives but future expenses consume it
    def test_3E_salary_arrives_but_future_expenses_consume_it(self):
        p = make_profile(avail=5000.0, min_b=2000.0)
        sal_stream = RecurringStream(
            category="salary", description="Confirmed Salary", day_of_month=11, amount=10000.0, is_income=True
        )
        debt_stream = RecurringStream(
            category="debt_repayment", description="Recurring Debt", day_of_month=20, amount=9000.0, is_income=False
        )
        daily = self.engine.simulate_daily_balances(p, "2026-01-01", [sal_stream, debt_stream], 0.0, [])
        safe = self.engine.calculate_amount_safe_to_pay(daily, p.minimum_balance_to_keep, 8000.0)
        self.assertEqual(safe, 3000.0)
        # On Jan 11 (first salary), paying 8000 would cause breach on Jan 20 (balance falls below 2000)
        # And every month 9000 is consumed, so 8000 is never safe
        earliest = self.engine.find_earliest_date_for_full_payment(daily, p.minimum_balance_to_keep, 8000.0, "2026-01-01", salary_day=11)
        self.assertIsNone(earliest)

    # PHASE 4: Transaction Lifecycle states
    def test_4_lifecycle_states(self):
        p = make_profile(avail=10000.0, min_b=2000.0)
        events = [
            # 1. Pending debit: MUST be deducted
            FinancialEvent("e_p_deb", p.user_id, "expense", "Pending card hold", "shopping", "debit", 1000.0, "USD", "2026-01-02", "2026-01-02", "pending", normalized_amount=1000.0),
            # 2. Pending credit: MUST NOT be counted
            FinancialEvent("e_p_cred", p.user_id, "income", "Pending bonus", "salary", "credit", 5000.0, "USD", "2026-01-03", "2026-01-03", "pending", normalized_amount=5000.0),
            # 3. Cancelled debit: MUST NOT reduce cash
            FinancialEvent("e_c_deb", p.user_id, "expense", "Cancelled order", "shopping", "debit", 3000.0, "USD", "2026-01-04", "2026-01-04", "cancelled", normalized_amount=3000.0),
            # 4. Unrealized investment: MUST NOT count as cash
            FinancialEvent("e_unreal", p.user_id, "asset", "Stock surge", "investment", "credit", 10000.0, "USD", "2026-01-05", "2026-01-05", "unrealized", normalized_amount=10000.0),
            # 5. Failed debit: MUST NOT reduce cash
            FinancialEvent("e_fail", p.user_id, "expense", "Failed wire", "transfer", "debit", 2000.0, "USD", "2026-01-06", "2026-01-06", "failed", normalized_amount=2000.0),
        ]
        daily = self.engine.simulate_daily_balances(p, "2026-01-01", [], 0.0, events)
        # End balance should be: 10000 - 1000 (pending debit only) = 9000.0
        final_bal = daily[-1][1]
        self.assertEqual(final_bal, 9000.0)

    # PHASE 6: Minimum Balance Stress Tests
    def test_6_minimum_balance_stress_boundaries(self):
        # 1. Exactly equals minimum
        p1 = make_profile(avail=2000.0, min_b=2000.0)
        d1 = self.engine.simulate_daily_balances(p1, "2026-01-01", [], 0.0, [])
        self.assertEqual(self.engine.calculate_amount_safe_to_pay(d1, 2000.0, 100.0), 0.0)
        
        # 2. One cent above minimum
        p2 = make_profile(avail=2000.01, min_b=2000.0)
        d2 = self.engine.simulate_daily_balances(p2, "2026-01-01", [], 0.0, [])
        self.assertEqual(self.engine.calculate_amount_safe_to_pay(d2, 2000.0, 100.0), 0.01)

        # 3. One cent below minimum
        p3 = make_profile(avail=1999.99, min_b=2000.0)
        d3 = self.engine.simulate_daily_balances(p3, "2026-01-01", [], 0.0, [])
        self.assertEqual(self.engine.calculate_amount_safe_to_pay(d3, 2000.0, 100.0), 0.0)

if __name__ == "__main__":
    unittest.main()
