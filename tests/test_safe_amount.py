import os
import sys
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.cashflow import CashFlowEngine

class TestSafeAmountAndEarliestDate(unittest.TestCase):
    def setUp(self):
        self.engine = CashFlowEngine(horizon_days=90)

    # PHASE 7: amount_safe_to_pay tests
    def test_7_zero_capacity(self):
        daily = [("2026-01-01", 2000.0), ("2026-01-02", 2000.0)]
        safe = self.engine.calculate_amount_safe_to_pay(daily, 2000.0, 5000.0)
        self.assertEqual(safe, 0.0)

    def test_7_partial_capacity(self):
        daily = [("2026-01-01", 6250.0), ("2026-01-02", 6250.0)]
        safe = self.engine.calculate_amount_safe_to_pay(daily, 2000.0, 10000.0)
        self.assertEqual(safe, 4250.0)

    def test_7_capacity_greater_than_request(self):
        daily = [("2026-01-01", 25000.0), ("2026-01-02", 22000.0)]
        # Buffer is 22000 - 2000 = 20000, requested is 10000
        safe = self.engine.calculate_amount_safe_to_pay(daily, 2000.0, 10000.0)
        self.assertEqual(safe, 10000.0)  # Capped at requested_amount

    def test_7_negative_calculated_capacity_clamps_to_zero(self):
        daily = [("2026-01-01", 1500.0), ("2026-01-02", 1200.0)]
        # Min balance is 2000, buffer is -800
        safe = self.engine.calculate_amount_safe_to_pay(daily, 2000.0, 5000.0)
        self.assertEqual(safe, 0.0)

    # PHASE 8: earliest_date_for_full_payment tests
    def test_8_immediately_affordable(self):
        daily = [("2026-01-01", 10000.0), ("2026-01-02", 10000.0)]
        earliest = self.engine.find_earliest_date_for_full_payment(daily, 2000.0, 5000.0, "2026-01-01")
        self.assertEqual(earliest, "2026-01-01")

    def test_8_salary_dependent(self):
        daily = [
            ("2026-01-01", 3000.0),  # Not safe for 5000
            ("2026-01-14", 3000.0),
            ("2026-01-15", 13000.0), # Payday!
            ("2026-01-16", 13000.0)
        ]
        earliest = self.engine.find_earliest_date_for_full_payment(daily, 2000.0, 5000.0, "2026-01-01", salary_day=15)
        self.assertEqual(earliest, "2026-01-15")

    def test_8_temporary_affordability_rejected(self):
        # Scenario: Balance temporarily surges to 10000 on Jan 10, but drops to 2500 on Jan 15.
        # If user pays 5000 on Jan 10, balance on Jan 15 becomes 2500 - 5000 = -2500 < 2000 min!
        daily = [
            ("2026-01-01", 3000.0),
            ("2026-01-10", 10000.0), # Surge
            ("2026-01-15", 2500.0)   # Drop
        ]
        earliest = self.engine.find_earliest_date_for_full_payment(daily, 2000.0, 5000.0, "2026-01-01")
        # Jan 10 must be REJECTED because future trajectory breaches min balance
        self.assertIsNone(earliest)

    def test_8_never_affordable(self):
        daily = [("2026-01-01", 3000.0), ("2026-01-30", 3500.0), ("2026-03-30", 3500.0)]
        earliest = self.engine.find_earliest_date_for_full_payment(daily, 2000.0, 5000.0, "2026-01-01")
        self.assertIsNone(earliest)

if __name__ == "__main__":
    unittest.main()
