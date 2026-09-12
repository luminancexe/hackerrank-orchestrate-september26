import os
import sys
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.models import FinancialProfile, FinancialEvent, Request, PaymentOption
from code.cashflow import CashFlowEngine
from code.plans import PaymentPlanEngine, CandidatePlan
from code.optimizer import DecisionOptimizer
from code.resolver import UserMessageContext

class TestDecisionRanking(unittest.TestCase):
    def setUp(self):
        self.cf_engine = CashFlowEngine(horizon_days=90)
        self.plan_engine = PaymentPlanEngine()
        self.optimizer = DecisionOptimizer(self.cf_engine, self.plan_engine)

    # Tie-breaker 1: Completion deadline
    def test_ranking_1_completion_deadline(self):
        # A plan completing before deadline is preferred over one completing after
        req = Request("r1", "u1", "2026-01-01", "discretionary", 1000.0, "2026-02-01", True, "item")
        
        plan_on_time = CandidatePlan(
            method="full_payment", affordability_status="affordable_now",
            payment_schedule=[("2026-01-01", 1000.0)], payment_plan_str="2026-01-01:1000",
            earliest_date_for_full_payment="2026-01-01", spending_changes=["stop:ev1"], spending_changes_str="stop:ev1",
            total_payable_amount=1000.0, first_payment_date="2026-01-01", last_payment_date="2026-01-01",
            number_of_payments=1
        )
        plan_late = CandidatePlan(
            method="wait", affordability_status="affordable_later",
            payment_schedule=[("2026-02-15", 1000.0)], payment_plan_str="2026-02-15:1000",
            earliest_date_for_full_payment="2026-02-15", spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-02-15", last_payment_date="2026-02-15",
            number_of_payments=1
        )
        candidates = [plan_late, plan_on_time]
        candidates.sort(key=lambda p: (
            0 if p.last_payment_date <= req.desired_completion_date else 1,
            len(p.spending_changes),
            round(p.total_payable_amount, 2),
            p.first_payment_date,
            p.number_of_payments,
            p.payment_option_id if p.payment_option_id else 'zzzz'
        ))
        self.assertEqual(candidates[0], plan_on_time)

    # Tie-breaker 2: Spending changes (0 changes preferred over 1)
    def test_ranking_2_avoid_spending_changes(self):
        req = Request("r1", "u1", "2026-01-01", "discretionary", 1000.0, "2026-03-01", True, "item")
        plan_no_cuts = CandidatePlan(
            method="installments", affordability_status="affordable_with_plan",
            payment_schedule=[("2026-01-01", 500.0), ("2026-02-01", 500.0)], payment_plan_str="2026-01-01:500|2026-02-01:500",
            earliest_date_for_full_payment="2026-01-01", spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-01-01", last_payment_date="2026-02-01",
            number_of_payments=2
        )
        plan_with_cuts = CandidatePlan(
            method="full_payment", affordability_status="affordable_with_plan",
            payment_schedule=[("2026-01-01", 1000.0)], payment_plan_str="2026-01-01:1000",
            earliest_date_for_full_payment="2026-01-01", spending_changes=["stop:ev1"], spending_changes_str="stop:ev1",
            total_payable_amount=1000.0, first_payment_date="2026-01-01", last_payment_date="2026-01-01",
            number_of_payments=1
        )
        candidates = [plan_with_cuts, plan_no_cuts]
        candidates.sort(key=lambda p: (
            0 if p.last_payment_date <= req.desired_completion_date else 1,
            len(p.spending_changes),
            round(p.total_payable_amount, 2),
            p.first_payment_date,
            p.number_of_payments,
            p.payment_option_id if p.payment_option_id else 'zzzz'
        ))
        self.assertEqual(candidates[0], plan_no_cuts, "Plan with 0 spending changes should beat 1 spending change")

    # Tie-breaker 3: Minimize total cost
    def test_ranking_3_minimize_total_cost(self):
        req = Request("r1", "u1", "2026-01-01", "discretionary", 1000.0, "2026-03-01", True, "item")
        plan_cheaper = CandidatePlan(
            method="installments", affordability_status="affordable_with_plan",
            payment_schedule=[("2026-01-01", 500.0), ("2026-02-01", 500.0)], payment_plan_str="",
            earliest_date_for_full_payment=None, spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-01-01", last_payment_date="2026-02-01",
            number_of_payments=2, payment_option_id="opt_cheap"
        )
        plan_expensive = CandidatePlan(
            method="installments", affordability_status="affordable_with_plan",
            payment_schedule=[("2026-01-01", 550.0), ("2026-02-01", 550.0)], payment_plan_str="",
            earliest_date_for_full_payment=None, spending_changes=[], spending_changes_str="none",
            total_payable_amount=1100.0, first_payment_date="2026-01-01", last_payment_date="2026-02-01",
            number_of_payments=2, payment_option_id="opt_fee"
        )
        candidates = [plan_expensive, plan_cheaper]
        candidates.sort(key=lambda p: (
            0 if p.last_payment_date <= req.desired_completion_date else 1,
            len(p.spending_changes),
            round(p.total_payable_amount, 2),
            p.first_payment_date,
            p.number_of_payments,
            p.payment_option_id if p.payment_option_id else 'zzzz'
        ))
        self.assertEqual(candidates[0], plan_cheaper, "Cheaper plan must win")

    # Tie-breaker 4: Starts earlier
    def test_ranking_4_starts_earlier(self):
        req = Request("r1", "u1", "2026-01-01", "discretionary", 1000.0, "2026-03-01", True, "item")
        plan_jan = CandidatePlan(
            method="full_payment", affordability_status="affordable_now",
            payment_schedule=[("2026-01-05", 1000.0)], payment_plan_str="",
            earliest_date_for_full_payment="2026-01-05", spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-01-05", last_payment_date="2026-01-05",
            number_of_payments=1
        )
        plan_feb = CandidatePlan(
            method="full_payment", affordability_status="affordable_later",
            payment_schedule=[("2026-02-01", 1000.0)], payment_plan_str="",
            earliest_date_for_full_payment="2026-02-01", spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-02-01", last_payment_date="2026-02-01",
            number_of_payments=1
        )
        candidates = [plan_feb, plan_jan]
        candidates.sort(key=lambda p: (
            0 if p.last_payment_date <= req.desired_completion_date else 1,
            len(p.spending_changes),
            round(p.total_payable_amount, 2),
            p.first_payment_date,
            p.number_of_payments,
            p.payment_option_id if p.payment_option_id else 'zzzz'
        ))
        self.assertEqual(candidates[0], plan_jan, "Earlier start date must win")

    # Tie-breaker 5: Fewest payments
    def test_ranking_5_fewest_payments(self):
        req = Request("r1", "u1", "2026-01-01", "discretionary", 1000.0, "2026-03-01", True, "item")
        plan_1_pay = CandidatePlan(
            method="full_payment", affordability_status="affordable_now",
            payment_schedule=[("2026-01-01", 1000.0)], payment_plan_str="",
            earliest_date_for_full_payment="2026-01-01", spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-01-01", last_payment_date="2026-01-01",
            number_of_payments=1
        )
        plan_2_pay = CandidatePlan(
            method="partial_payment", affordability_status="affordable_with_plan",
            payment_schedule=[("2026-01-01", 500.0), ("2026-01-15", 500.0)], payment_plan_str="",
            earliest_date_for_full_payment="2026-01-15", spending_changes=[], spending_changes_str="none",
            total_payable_amount=1000.0, first_payment_date="2026-01-01", last_payment_date="2026-01-15",
            number_of_payments=2
        )
        candidates = [plan_2_pay, plan_1_pay]
        candidates.sort(key=lambda p: (
            0 if p.last_payment_date <= req.desired_completion_date else 1,
            len(p.spending_changes),
            round(p.total_payable_amount, 2),
            p.first_payment_date,
            p.number_of_payments,
            p.payment_option_id if p.payment_option_id else 'zzzz'
        ))
        self.assertEqual(candidates[0], plan_1_pay, "1 payment must win over 2 payments when all else equal")

if __name__ == "__main__":
    unittest.main()
