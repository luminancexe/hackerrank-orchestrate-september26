import os
import sys
import csv
import time
import unittest

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from code.main import run_pipeline
from code.evaluation.main import evaluate_samples

class TestEndToEnd(unittest.TestCase):
    # PHASE 20: Full dataset execution & output verification
    def test_20_full_dataset_pipeline_execution(self):
        start_time = time.time()
        run_pipeline(data_dir="dataset")
        elapsed = time.time() - start_time
        
        # Performance check (< 10 seconds, typically ~2.5s)
        self.assertLess(elapsed, 10.0, f"Pipeline execution took {elapsed:.2f}s, exceeding 10s threshold")
        
        # Verify output exists
        self.assertTrue(os.path.exists("output.csv"), "output.csv was not generated")
        
        # Check columns and rows using csv
        expected_cols = [
            "request_id", "amount_safe_to_pay", "affordability_status",
            "recommended_payment_method", "payment_plan",
            "earliest_date_for_full_payment", "spending_changes_needed",
            "decision_explanation"
        ]
        with open("output.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, expected_cols)
            rows = list(reader)
        
        # Exactly 250 rows
        self.assertEqual(len(rows), 250, f"Expected 250 rows in output.csv, got {len(rows)}")
        
        valid_statuses = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
        valid_methods = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}

        # No nulls in mandatory columns
        for idx, row in enumerate(rows):
            for col in ["request_id", "amount_safe_to_pay", "affordability_status", "recommended_payment_method", "payment_plan", "spending_changes_needed", "decision_explanation"]:
                self.assertIsNotNone(row[col], f"Found None in column {col} at row {idx}")
                self.assertNotEqual(row[col], "", f"Found empty string in column {col} at row {idx}")

            self.assertIn(row["affordability_status"], valid_statuses)
            self.assertIn(row["recommended_payment_method"], valid_methods)

            # PHASE 24: Explanation Factuality & Grounding Check
            exp = row["decision_explanation"].strip()
            self.assertGreater(len(exp), 10, f"Explanation too short at row {idx}")
            self.assertLess(len(exp), 500, f"Explanation too long at row {idx}")

    # PHASE 21: Public Sample Benchmark Accuracy
    def test_21_public_sample_benchmark_accuracy(self):
        metrics = evaluate_samples(data_dir="dataset")
        total = 25

        # Assert high accuracy (payment method 25/25, plan 23/25, etc.)
        self.assertEqual(metrics["method_matches"], 25, f"Payment method matches: {metrics['method_matches']}/25")
        self.assertGreaterEqual(metrics["plan_matches"], 23, f"Plan matches: {metrics['plan_matches']}/25")
        self.assertGreaterEqual(metrics["status_matches"], 22, f"Status matches: {metrics['status_matches']}/25")
        self.assertGreaterEqual(metrics["changes_matches"], 22, f"Changes matches: {metrics['changes_matches']}/25")
        self.assertGreaterEqual(metrics["earliest_matches"], 21, f"Earliest matches: {metrics['earliest_matches']}/25")

if __name__ == "__main__":
    unittest.main()
